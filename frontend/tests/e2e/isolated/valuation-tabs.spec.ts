import { test, expect } from '@playwright/test';

test.describe('05 估值：Valuation 多 Tab 工具页', () => {
  test('页面加载，6 个估值工具 Tab 中至少 4 个可见', async ({ page }) => {
    await page.goto('/valuation');
    await expect(page.getByRole('heading', { name: /估值|Valuation/ }).first()).toBeVisible();
    const tabLabels = ['分位', '价格通道', '股息', 'EPS', '综合', '快照'];
    let visibleCount = 0;
    for (const label of tabLabels) {
      const candidate = page.getByText(label).first();
      if (await candidate.isVisible().catch(() => false)) visibleCount += 1;
    }
    expect(visibleCount).toBeGreaterThanOrEqual(4);
  });

  test('切到"历史快照"Tab，看到空态或快照表', async ({ page }) => {
    await page.goto('/valuation?code=600519');
    await page.getByRole('button', { name: '历史快照' }).click();
    await expect.poll(
      async () =>
        (await page.getByText(/暂无|无数据|尚无|无快照/).count()) +
        (await page.locator('.ant-table').count()),
      { timeout: 15_000 }
    ).toBeGreaterThan(0);
  });
});
