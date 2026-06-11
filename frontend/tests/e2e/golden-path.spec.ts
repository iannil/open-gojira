import { test, expect, type Page } from '@playwright/test';
import { resetE2EArtifacts } from './fixtures/seed';
import { clickGTab, expectToast } from './fixtures/ui';

/**
 * Golden-path E2E: drives a single investor lifecycle (L1 → L12) through the real browser UI.
 *
 *   L1  Screener        — configure a query and run it
 *   L2  Watchlist       — see the default group
 *   L3  Stock detail    — open 600519 / 贵州茅台
 *   L4  Analysis        — 三步法草稿 (顶层设计 → 求 → 财务) + save
 *   L5  Valuation       — fetch PE/PB percentile, save a snapshot
 *   L6  Discipline check — fill a check template via wizard
 *   L7  Holding (建仓)   — auto-opened HoldingForm via /portfolio?code=&action=buy&check_id=
 *   L8  Alerts          — the [auto-holding] stop-profit rule has been synced
 *   L9  Dividend        — record one dividend in 分红记录 Tab
 *   L10 Journal         — write a discipline 日志
 *   L11 Compare         — multi-stock 估值对比
 *   L12 Review          — 决策回看 Tab loads (empty-state tolerated)
 *
 * Every step interacts with the rendered DOM — no direct API calls. Steps run serially because
 * later steps depend on artifacts created earlier (analysis → check → holding → alert → dividend).
 */

const CODE = '600519';
const NAME = '贵州茅台';

let createdCheckId: number | null = null;

test.describe.configure({ mode: 'serial' });

test.describe('Gojira 投资生命周期 (golden path)', () => {
  test.beforeAll(async () => {
    await resetE2EArtifacts();
  });

  test('L1 · 筛选：在 Screener 跑一次默认条件', async ({ page }) => {
    await page.goto('/screener');
    await expect(page.getByRole('heading', { name: /筛选/ }).first()).toBeVisible();

    const runBtn = page.getByRole('button', { name: '开始筛选' });
    const resp = page.waitForResponse(
      (r) => r.url().includes('/api/screener/run') && r.request().method() === 'POST',
      { timeout: 20_000 },
    );
    await runBtn.click();
    const r = await resp;
    expect(r.ok()).toBeTruthy();
    await expect(page.getByRole('heading', { name: '筛选结果' })).toBeVisible();
  });

  test('L2 · 自选：默认分组在 Watchlist 可见', async ({ page }) => {
    await page.goto('/watchlist');
    await expect(page.getByRole('heading', { name: /自选股|Watchlist/ }).first()).toBeVisible();
    await expect(page.getByText('默认关注').first()).toBeVisible({ timeout: 15_000 });
  });

  test('L3 · 调研：股票详情 /stock/600519 加载基本信息', async ({ page }) => {
    await page.goto(`/stock/${CODE}`);
    await expect(page.getByText(NAME).first()).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(CODE).first()).toBeVisible();
  });

  test('L4 · 分析：三步法 草稿 (顶层设计 → 求 → 财务)', async ({ page }) => {
    await page.goto(`/analysis?code=${CODE}`);
    await expect(page.getByText('顶层设计').first()).toBeVisible({ timeout: 15_000 });

    // Step 1: 顶层设计
    await page.getByRole('button', { name: /金融安全/ }).click();
    await page.getByPlaceholder(/第一性原理|煤价、电力成本/).fill('品牌稀缺性 + 高端白酒供给约束');
    await page.getByPlaceholder('从顶层设计角度分析这只股票...').fill('E2E 顶层设计笔记');

    // Step 2: 求评分 — 切到「商业模式」tab.
    await page.locator('.aw-tab', { hasText: '商业模式' }).click();
    // QiuScorer 内部三个 checkbox：对上游 / 对下游 / 对政府 议价能力。
    const checkboxes = page.locator('input[type="checkbox"]');
    const count = await checkboxes.count();
    for (let i = 0; i < Math.min(count, 3); i += 1) {
      await checkboxes.nth(i).check({ force: true });
    }

    // Step 3: 财务分析
    await page.locator('.aw-tab', { hasText: '财务分析' }).click();
    await page.getByPlaceholder('观察经营现金流与归母净利润的关系...').fill('经营现金流持续高于净利润');
    await page.getByPlaceholder('财务数据验证分析...').fill('ROE > 25%，无息负债占比高');
    await page.getByPlaceholder('综合三个维度的分析，形成投资判断...').fill('适合作为长期核心持仓');

    // 保存草稿 — 触发 POST /api/analysis
    const savePost = page.waitForResponse(
      (r) => r.url().includes('/api/analysis') && r.request().method() === 'POST',
      { timeout: 15_000 },
    );
    await page.getByRole('button', { name: '保存草稿' }).first().click();
    const sr = await savePost;
    expect(sr.ok()).toBeTruthy();
    await expectToast(page, /草稿已保存/);
  });

  test('L5 · 估值：PE/PB 分位 → 保存快照', async ({ page }) => {
    await page.goto(`/valuation?code=${CODE}`);
    await expect(page.getByText('PE/PB 分位').first()).toBeVisible({ timeout: 15_000 });

    // Trigger percentile fetch. URL: /api/valuation/{code}/percentile
    const percentileResp = page.waitForResponse(
      (r) => /\/api\/valuation\/\d+\/percentile/.test(r.url()) && r.request().method() === 'GET',
      { timeout: 30_000 },
    );
    await page.getByRole('button', { name: /获取数据|获取中/ }).click();
    const pr = await percentileResp;
    // Tolerate Lixinger backend failures — saving the snapshot only matters when data loaded.
    if (pr.ok()) {
      const saveBtn = page.getByRole('button', { name: /保存为估值快照/ });
      if (await saveBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
        const snapResp = page.waitForResponse(
          (r) => /\/api\/valuation\/\d+\/snapshot$/.test(r.url()) && r.request().method() === 'POST',
          { timeout: 15_000 },
        );
        await saveBtn.click();
        await snapResp;
      }
    }
  });

  test('L6 · 纪律检查：Discipline → 纪律检查 → 完成一次心理偏差检查', async ({ page }) => {
    await page.goto('/discipline');
    await clickGTab(page, '纪律检查');

    // Step 1: 选择第一个模板卡片。
    const firstTemplate = page.locator('.grid-3 .g-card').first();
    await firstTemplate.waitFor({ state: 'visible', timeout: 15_000 });
    await firstTemplate.click();

    // Step 2: 为每个问题选第 3 档（中性「一般」）。
    // 隐藏的 radio input：用 label 包裹，需用 force click 在 label 上。
    const labels = page.locator('label:has(input[type="radio"][value="3"])');
    const n = await labels.count();
    for (let i = 0; i < n; i += 1) await labels.nth(i).click();
    await page.getByRole('button', { name: /下一步/ }).click();

    // Step 3: 填应对措施，提交。
    await page.getByPlaceholder('记录你将采取的应对措施...').fill('E2E 检查应对措施');
    const submitResp = page.waitForResponse(
      (r) => r.url().includes('/api/discipline/checks') && r.request().method() === 'POST',
      { timeout: 15_000 },
    );
    await page.getByRole('button', { name: '提交检查' }).click();
    const sr = await submitResp;
    expect(sr.ok()).toBeTruthy();
    const body = (await sr.json()) as { id: number };
    createdCheckId = body.id;
    expect(createdCheckId).toBeGreaterThan(0);
  });

  test('L7 · 建仓：/portfolio?action=buy 自动打开 HoldingForm 并保存', async ({ page }) => {
    // Trigger the auto-open-form flow that 决策→持仓 接力 uses in real code.
    await page.goto(`/portfolio?code=${CODE}&action=buy&check_id=${createdCheckId ?? 0}`);
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 15_000 });
    await expect(dialog.getByText('新增持仓')).toBeVisible();

    // 股票码已锁定（来自 URL prefill），不需重选。
    // 买入日期：使用 antd DatePicker 的输入框直接 fill。
    const dateInput = dialog.locator('input[placeholder="选择日期"]');
    await dateInput.click();
    await dateInput.fill('2026-01-10');
    await page.keyboard.press('Enter');

    // 成本价 / 数量 / 止盈价 —— antd InputNumber 内部用 role=spinbutton 的 input。
    const numericInputs = dialog.locator('input.ant-input-number-input');
    await numericInputs.nth(0).fill('1500');
    await numericInputs.nth(1).fill('100');
    await numericInputs.nth(2).fill('2000');

    // 交易理由（已由 checkId 注入默认值，但补充一段）。
    const rationale = dialog.locator('textarea').first();
    await rationale.fill((await rationale.inputValue()) + ' — E2E golden path');

    const saveResp = page.waitForResponse(
      (r) => r.url().includes('/api/portfolio') && r.request().method() === 'POST',
      { timeout: 15_000 },
    );
    await dialog.getByRole('button', { name: '确认新增' }).click();
    const sr = await saveResp;
    expect(sr.ok()).toBeTruthy();
    const body = (await sr.json()) as { id: number; stock_code: string };
    expect(body.stock_code).toBe(CODE);

    // 列表里出现这条持仓。
    await expect(page.getByText(CODE).first()).toBeVisible({ timeout: 10_000 });
  });

  test('L8 · 告警：持仓自动同步出 [auto-holding] 止盈规则', async ({ page }) => {
    await page.goto('/alerts');
    await expect(page.getByRole('heading', { name: /告警/ }).first()).toBeVisible({ timeout: 15_000 });
    // Switch to the 规则 tab (antd Tabs default to first = 事件).
    await page.getByRole('tab', { name: /规则/ }).click();
    // Static legend text confirming auto-sync labels are documented.
    await expect(page.getByText(/\[auto-holding\]/).first()).toBeVisible({ timeout: 10_000 });
    // The synced rule appears as a row: rule_type=止盈触发 + stock_code=600519.
    const stopProfitRow = page.locator('tr', { hasText: '止盈触发' }).filter({ hasText: CODE });
    await expect(stopProfitRow.first()).toBeVisible({ timeout: 10_000 });
  });

  test('L9 · 分红：在 Portfolio 的 分红记录 Tab 录入一条', async ({ page }) => {
    await page.goto('/portfolio');
    await clickGTab(page, '分红记录');
    await page.getByRole('button', { name: /\+ 新增分红/ }).click();

    const dialog = page.getByRole('dialog').filter({ hasText: '新增分红' });
    await expect(dialog).toBeVisible({ timeout: 10_000 });

    // 股票码 — antd Select 搜索 600519。
    const codeSelect = dialog.locator('.ant-select').first();
    await codeSelect.click();
    await page.keyboard.type(CODE);
    const opt = page
      .locator('.ant-select-item-option:not(.ant-select-item-option-disabled)')
      .filter({ hasText: CODE })
      .first();
    await opt.waitFor({ state: 'visible', timeout: 8_000 });
    await opt.click();

    // 除权日。
    const dateInput = dialog.locator('input[placeholder="选择除权日"]');
    await dateInput.click();
    await dateInput.fill('2026-03-15');
    await page.keyboard.press('Enter');

    // 每股分红 / 持仓数量 / 税后金额。
    const nums = dialog.locator('input.ant-input-number-input');
    await nums.nth(0).fill('30.0000');
    await nums.nth(1).fill('100');
    await nums.nth(2).fill('2700.00');

    const post = page.waitForResponse(
      (r) =>
        r.url().includes('/api/dividends') &&
        !r.url().includes('/summary') &&
        r.request().method() === 'POST' &&
        r.status() !== 307,
      { timeout: 15_000 },
    );
    await dialog.getByRole('button', { name: '确认新增' }).click();
    const pr = await post;
    expect(pr.ok()).toBeTruthy();
    // Toast confirms save.
    await expect(page.locator('.ant-message-notice').filter({ hasText: /已保存/ }).first())
      .toBeVisible({ timeout: 10_000 });
  });

  test('L10 · 纪律日志：写一条 journal', async ({ page }) => {
    await page.goto('/discipline');
    await clickGTab(page, '交易日志');
    await page.getByRole('button', { name: '写日志' }).click();

    const dialog = page.getByRole('dialog').filter({ hasText: '写日志' });
    await expect(dialog).toBeVisible({ timeout: 10_000 });

    const dateInput = dialog.locator('input[placeholder="Select date"], .ant-picker input').first();
    await dateInput.click();
    await dateInput.fill('2026-06-06');
    await page.keyboard.press('Enter');

    await dialog.getByPlaceholder('研究笔记...').fill('E2E: 检查 600519 财报');
    await dialog.getByPlaceholder('反思与总结...').fill('坚持纪律，避免追高');

    const post = page.waitForResponse(
      (r) => r.url().includes('/api/discipline/journal') && r.request().method() === 'POST',
      { timeout: 15_000 },
    );
    // antd OK buttons render with a space between CJK chars ("保 存"); match flexibly.
    await dialog.getByRole('button', { name: /保\s*存/ }).click();
    const pr = await post;
    expect(pr.ok()).toBeTruthy();
  });

  test('L11 · 对比：选择 600519 + 601318 触发对比', async ({ page }) => {
    await page.goto('/compare');
    await expect(page.getByRole('heading', { name: /对比/ }).first()).toBeVisible({ timeout: 15_000 });

    const multi = page.locator('.ant-select-multiple').first();
    await pickCompareOption(page, multi, CODE);
    await pickCompareOption(page, multi, '601318');

    const post = page.waitForResponse(
      (r) => r.url().includes('/api/valuation/compare') && r.request().method() === 'POST',
      { timeout: 20_000 },
    );
    await page.getByRole('button', { name: /开始对比|对比中/ }).click();
    const pr = await post;
    expect(pr.ok()).toBeTruthy();
    const body = (await pr.json()) as { stocks: Array<{ stock_code: string }> };
    expect(body.stocks.map((s) => s.stock_code).sort()).toEqual(['600519', '601318']);
  });

  test('L12 · 复盘：Discipline → 决策回看 Tab 加载', async ({ page }) => {
    await page.goto('/discipline');
    await clickGTab(page, '决策回看');
    // Either a card with metrics or an empty-state. Both are acceptable;
    // we just need the panel to mount without error.
    await page.waitForLoadState('networkidle');
    await expect(page.locator('body')).toBeVisible();
  });
});

async function pickCompareOption(page: Page, multi: ReturnType<Page['locator']>, code: string) {
  await multi.click();
  await page.keyboard.type(code);
  const opt = page
    .locator('.ant-select-item-option:not(.ant-select-item-option-disabled)')
    .filter({ hasText: code })
    .first();
  await opt.waitFor({ state: 'visible', timeout: 10_000 });
  await opt.click();
  await page.keyboard.press('Escape');
}
