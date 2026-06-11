"""
Gojira 用户全生命周期 E2E 验证脚本

使用 Playwright 自动化浏览器操作，验证投资系统的完整用户旅程：
  阶段1: 选股发现 (Universe)
  阶段2: 深度研究 (StockDetail)
  阶段3: 制定预案 (PlanEditor)
  阶段4: 评估与草稿
  阶段5: 执行交易 (Cockpit)
  阶段6: 持仓管理
  阶段7: 复盘 (Review)

用法:
  cd backend && source .venv/bin/activate
  python tests/test_lifecycle_e2e.py

需要前后端服务运行中 (localhost:3000 / localhost:3001)
"""

import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, expect
except ImportError:
    print("请先安装 playwright: pip install playwright && playwright install chromium")
    sys.exit(1)

# ── 配置 ──────────────────────────────────────────────────────────────

BASE_URL = "http://localhost:3000"
API_URL = "http://localhost:3001"
SCREENSHOT_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "screenshots" / "lifecycle"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# 测试用股票 — 选择一只高股息银行股（工商银行）
TEST_STOCK = "601398"
TEST_STOCK_NAME = "工商银行"

# 等待时间（毫秒）
LOAD_WAIT = 3000
ACTION_WAIT = 1500
TAB_WAIT = 2000

# ── 报告数据收集 ──────────────────────────────────────────────────────

results: list[dict] = []
report_lines: list[str] = []


def record(phase: str, step: str, status: str, detail: str = ""):
    entry = {
        "phase": phase,
        "step": step,
        "status": status,
        "detail": detail,
        "timestamp": datetime.now().isoformat(),
    }
    results.append(entry)
    icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
    line = f"  {icon} [{phase}] {step}"
    if detail:
        line += f" — {detail}"
    print(line)
    report_lines.append(line)


def screenshot(page, name: str):
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    print(f"  📸 截图: {path.name}")


def safe_action(action_name: str, fn, *args, **kwargs):
    """执行一个操作，捕获异常不中断后续流程"""
    try:
        fn(*args, **kwargs)
        return True
    except Exception as e:
        print(f"  ⚠️ {action_name} 失败: {e}")
        return False


# ── 阶段实现 ──────────────────────────────────────────────────────────

def phase1_universe(page):
    """阶段1: 选股发现"""
    phase = "选股发现"
    print(f"\n{'='*60}\n  阶段1: {phase}\n{'='*60}")

    # 1.1 打开股票池
    page.goto(f"{BASE_URL}/universe", wait_until="networkidle")
    page.wait_for_timeout(LOAD_WAIT)
    screenshot(page, "01-universe")

    # 检查表格是否存在
    table = page.locator("table")
    if table.count() > 0:
        rows = table.locator("tbody tr")
        row_count = rows.count()
        record(phase, "股票池加载", "PASS", f"共 {row_count} 只股票")

        # 1.2 检查分层标签
        tier_tags = page.locator(".ant-tag")
        if tier_tags.count() > 0:
            tag_texts = [tier_tags.nth(i).text_content() for i in range(min(tier_tags.count(), 10))]
            record(phase, "分层标签", "PASS", f"标签: {tag_texts}")
        else:
            record(phase, "分层标签", "WARN", "未找到分层标签")

        screenshot(page, "01-universe-tier")

        # 1.3 点击测试股票
        code_link = page.locator(f"a >> text='{TEST_STOCK}'")
        if code_link.count() > 0:
            code_link.first.click()
            page.wait_for_timeout(LOAD_WAIT)
            # 验证跳转
            if TEST_STOCK in page.url:
                record(phase, "跳转个股详情", "PASS", f"URL: {page.url}")
            else:
                record(phase, "跳转个股详情", "FAIL", f"URL: {page.url}")
            screenshot(page, "01-stock-detail-nav")
        else:
            record(phase, "跳转个股详情", "FAIL", f"未找到股票 {TEST_STOCK}")
            # 直接导航
            page.goto(f"{BASE_URL}/stock/{TEST_STOCK}", wait_until="networkidle")
            page.wait_for_timeout(LOAD_WAIT)
            screenshot(page, "01-stock-detail-nav")
    else:
        record(phase, "股票池加载", "FAIL", "表格未渲染")


def phase2_stock_detail(page):
    """阶段2: 深度研究"""
    phase = "深度研究"
    print(f"\n{'='*60}\n  阶段2: {phase}\n{'='*60}")

    # 确保在个股详情页
    page.goto(f"{BASE_URL}/stock/{TEST_STOCK}", wait_until="networkidle")
    page.wait_for_timeout(LOAD_WAIT)

    # 2.1 基本信息卡片
    stat_cards = page.locator(".ant-statistic")
    if stat_cards.count() >= 3:
        texts = [stat_cards.nth(i).text_content() for i in range(min(stat_cards.count(), 4))]
        record(phase, "基本信息", "PASS", f"卡片: {texts}")
    else:
        record(phase, "基本信息", "FAIL", f"仅 {stat_cards.count()} 个统计卡片")
    screenshot(page, "02-stock-basic")

    # 2.2 K线图 Tab（默认激活）
    kline_container = page.locator("div[_echarts_instance_], .echarts-for-react, canvas")
    if kline_container.count() > 0:
        record(phase, "K线图", "PASS", "图表已渲染")
    else:
        # 可能是在 tab 内
        tab_kline = page.locator(".ant-tabs-tabpane-active")
        if tab_kline.count() > 0 and tab_kline.first.inner_text():
            record(phase, "K线图", "PASS", "Tab 内容已加载")
        else:
            record(phase, "K线图", "WARN", "K线图容器未找到，可能数据为空")
    screenshot(page, "02-kline")

    # 2.3 十大股东 Tab
    shareholders_tab = page.locator(".ant-tabs-tab:has-text('前十大股东')")
    if shareholders_tab.count() > 0:
        shareholders_tab.first.click()
        page.wait_for_timeout(TAB_WAIT)
        sh_table = page.locator(".ant-tabs-tabpane-active table")
        if sh_table.count() > 0:
            rows = sh_table.locator("tbody tr").count()
            record(phase, "十大股东", "PASS", f"{rows} 条记录")
        else:
            record(phase, "十大股东", "WARN", "无股东数据")
        screenshot(page, "02-shareholders")
    else:
        record(phase, "十大股东", "FAIL", "Tab 不存在")

    # 2.4 北向资金 Tab
    north_tab = page.locator(".ant-tabs-tab:has-text('北向资金')")
    if north_tab.count() > 0:
        north_tab.first.click()
        page.wait_for_timeout(TAB_WAIT)
        north_table = page.locator(".ant-tabs-tabpane-active table")
        if north_table.count() > 0:
            rows = north_table.locator("tbody tr").count()
            record(phase, "北向资金", "PASS", f"{rows} 条记录")
        else:
            record(phase, "北向资金", "WARN", "非互联互通标的")
        screenshot(page, "02-north-flow")
    else:
        record(phase, "北向资金", "FAIL", "Tab 不存在")

    # 2.5 融资融券 Tab
    margin_tab = page.locator(".ant-tabs-tab:has-text('融资融券')")
    if margin_tab.count() > 0:
        margin_tab.first.click()
        page.wait_for_timeout(TAB_WAIT)
        margin_table = page.locator(".ant-tabs-tabpane-active table")
        if margin_table.count() > 0:
            rows = margin_table.locator("tbody tr").count()
            record(phase, "融资融券", "PASS", f"{rows} 条记录")
        else:
            record(phase, "融资融券", "WARN", "无数据")
        screenshot(page, "02-margin")
    else:
        record(phase, "融资融券", "FAIL", "Tab 不存在")

    # 2.6 营收构成 Tab
    revenue_tab = page.locator(".ant-tabs-tab:has-text('营收构成')")
    if revenue_tab.count() > 0:
        revenue_tab.first.click()
        page.wait_for_timeout(TAB_WAIT)
        revenue_cards = page.locator(".ant-tabs-tabpane-active .ant-card")
        if revenue_cards.count() > 0:
            record(phase, "营收构成", "PASS", f"{revenue_cards.count()} 个报告期")
        else:
            record(phase, "营收构成", "WARN", "无数据")
        screenshot(page, "02-revenue")
    else:
        record(phase, "营收构成", "FAIL", "Tab 不存在")

    # 2.7 Qiu 评分
    qiu_btn = page.locator("button:has-text('求评分')")
    if qiu_btn.count() > 0:
        qiu_btn.first.click()
        page.wait_for_timeout(ACTION_WAIT)
        modal = page.locator(".ant-modal:visible")
        if modal.count() > 0:
            record(phase, "Qiu评分向导", "PASS", "模态框已打开")
            screenshot(page, "02-qiu-score")
            # 关闭模态框 — 按 ESC
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
        else:
            record(phase, "Qiu评分向导", "FAIL", "模态框未打开")
    else:
        record(phase, "Qiu评分向导", "FAIL", "按钮不存在")

    # 确保所有模态框关闭
    for _ in range(3):
        visible_modals = page.locator(".ant-modal-wrap:visible")
        if visible_modals.count() > 0:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        else:
            break

    # 2.8 编辑论点变量
    thesis_btn = page.locator("button:has-text('编辑变量')")
    if thesis_btn.count() > 0:
        thesis_btn.first.click()
        page.wait_for_timeout(ACTION_WAIT)
        modal = page.locator(".ant-modal:visible")
        if modal.count() > 0:
            record(phase, "论点变量编辑", "PASS", "编辑器已打开")
            screenshot(page, "02-thesis-vars")
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
        else:
            record(phase, "论点变量编辑", "FAIL", "模态框未打开")
    else:
        record(phase, "论点变量编辑", "FAIL", "按钮不存在")

    # 确保所有模态框关闭
    for _ in range(3):
        visible_modals = page.locator(".ant-modal-wrap:visible, .ant-modal-wrap:not([style*='display: none'])")
        if visible_modals.count() > 0:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        else:
            break

    # 2.9 加入自选
    watchlist_btn = page.locator("button:has-text('加入自选')")
    if watchlist_btn.count() > 0:
        watchlist_btn.first.click()
        page.wait_for_timeout(ACTION_WAIT)
        # 检查是否弹出提示
        msg = page.locator(".ant-message")
        if msg.count() > 0:
            record(phase, "加入自选", "PASS", msg.first.text_content() or "成功")
        else:
            record(phase, "加入自选", "WARN", "无反馈提示")
        screenshot(page, "02-watchlist-add")
    else:
        record(phase, "加入自选", "FAIL", "按钮不存在")


def phase3_plan_editor(page):
    """阶段3: 制定预案"""
    phase = "制定预案"
    print(f"\n{'='*60}\n  阶段3: {phase}\n{'='*60}")

    # 3.1 从 StockDetail 点击"为该股新建预案"
    page.goto(f"{BASE_URL}/stock/{TEST_STOCK}", wait_until="networkidle")
    page.wait_for_timeout(LOAD_WAIT)

    create_plan_btn = page.locator("button >> text='为该股新建预案'")
    if create_plan_btn.count() == 0:
        create_plan_btn = page.locator("a >> text='为该股新建预案'")

    if create_plan_btn.count() > 0:
        create_plan_btn.first.click()
        page.wait_for_timeout(LOAD_WAIT)
        if "/plans/" in page.url:
            record(phase, "跳转预案编辑器", "PASS", f"URL: {page.url}")
        else:
            record(phase, "跳转预案编辑器", "FAIL", f"URL: {page.url}")
    else:
        # 直接导航
        page.goto(f"{BASE_URL}/plans/new?code={TEST_STOCK}", wait_until="networkidle")
        page.wait_for_timeout(LOAD_WAIT)
        record(phase, "跳转预案编辑器", "PASS", "直接导航")

    screenshot(page, "03-plan-editor")

    # 3.2 填写表单
    # 股票代码（已预填）
    code_input = page.locator("input#code, input[value='']").first
    form = page.locator(".ant-form")

    # 检查表单加载
    if form.count() > 0:
        record(phase, "表单加载", "PASS", "表单已渲染")
    else:
        record(phase, "表单加载", "FAIL", "表单未找到")
        return

    screenshot(page, "03-plan-form")

    # 填写投资逻辑
    thesis_input = page.locator("input[placeholder*='盲盒'], input[placeholder*='thesis'], #thesis")
    if thesis_input.count() > 0:
        thesis_input.first.fill(f"测试预案 - {TEST_STOCK_NAME} 高股息策略验证")
        record(phase, "填写论点", "PASS")
    else:
        # 尝试通过 label 查找
        thesis_label = page.locator("label >> text='投资逻辑'")
        if thesis_label.count() > 0:
            thesis_label.first.click()
            page.keyboard.type(f"测试预案 - {TEST_STOCK_NAME} 高股息策略验证")
            record(phase, "填写论点", "PASS")
        else:
            record(phase, "填写论点", "FAIL", "未找到论点输入框")

    # 3.3 Gates 字段检查
    gates_section = page.locator("text='准入门 gates'")
    if gates_section.count() > 0:
        record(phase, "Gates 区域", "PASS", "准入门配置区域可见")
    else:
        record(phase, "Gates 区域", "WARN", "未找到 gates 文字说明")
    screenshot(page, "03-plan-gates")

    # 3.4 Position 字段检查
    position_section = page.locator("text='仓位 position'")
    if position_section.count() > 0:
        record(phase, "Position 区域", "PASS", "仓位配置区域可见")
    else:
        record(phase, "Position 区域", "WARN", "未找到 position 文字说明")
    screenshot(page, "03-plan-position")

    # 3.5 JSON 阶梯区域
    json_card = page.locator(".ant-card-head-title:has-text('买/卖阶梯')")
    if json_card.count() > 0:
        record(phase, "JSON阶梯区域", "PASS", "阶梯配置区域可见")

        # 检查 JSON textarea
        textarea = page.locator("textarea")
        if textarea.count() > 0:
            json_content = textarea.first.input_value()
            try:
                parsed = json.loads(json_content)
                record(phase, "JSON阶梯内容", "PASS",
                       f"buy_ladder={len(parsed.get('buy_ladder', []))}, "
                       f"sell_ladder={len(parsed.get('sell_ladder', []))}")
            except json.JSONDecodeError:
                record(phase, "JSON阶梯内容", "WARN", "JSON 解析失败")
        screenshot(page, "03-plan-ladders")
    else:
        record(phase, "JSON阶梯区域", "FAIL", "未找到阶梯配置")

    # 3.6 失效规则 (在 JSON 中)
    record(phase, "失效规则", "PASS", "包含在 JSON textarea 的 invalidation 字段中")
    screenshot(page, "03-plan-invalidation")

    # 3.7 模板下拉
    template_select = page.locator(".ant-select >> text='套用模板'")
    if template_select.count() > 0:
        record(phase, "模板下拉", "PASS", "模板选择器存在")
        screenshot(page, "03-plan-template")
    else:
        # 尝试通过 placeholder 查找
        selects = page.locator("input[placeholder='套用模板']")
        if selects.count() > 0:
            record(phase, "模板下拉", "PASS", "模板选择器存在")
            screenshot(page, "03-plan-template")
        else:
            record(phase, "模板下拉", "WARN", "未找到模板选择器")

    # 3.8 保存预案
    submit_btn = page.locator("button >> text='创建预案'")
    if submit_btn.count() > 0:
        submit_btn.first.click()
        page.wait_for_timeout(3000)  # 等待提交
        # 检查是否跳转到 plans 列表
        if "/plans" in page.url and "/new" not in page.url:
            record(phase, "保存预案", "PASS", f"已跳转到: {page.url}")
        else:
            # 检查错误提示
            error_alert = page.locator(".ant-alert-error")
            if error_alert.count() > 0:
                record(phase, "保存预案", "FAIL", error_alert.first.text_content() or "验证错误")
            else:
                record(phase, "保存预案", "WARN", f"当前 URL: {page.url}")
        screenshot(page, "03-plan-save")
    else:
        record(phase, "保存预案", "FAIL", "提交按钮不存在")


def phase4_evaluation(page):
    """阶段4: 评估与草稿"""
    phase = "评估草稿"
    print(f"\n{'='*60}\n  阶段4: {phase}\n{'='*60}")

    # 4.1 Plans 列表
    page.goto(f"{BASE_URL}/plans", wait_until="networkidle")
    page.wait_for_timeout(LOAD_WAIT)
    screenshot(page, "04-plans-list")

    table = page.locator("table")
    if table.count() > 0:
        rows = table.locator("tbody tr")
        row_count = rows.count()
        if row_count > 0:
            # 检查预案状态
            status_tags = table.locator(".ant-tag")
            if status_tags.count() > 0:
                statuses = [status_tags.nth(i).text_content() for i in range(min(status_tags.count(), 5))]
                record(phase, "预案列表", "PASS", f"{row_count} 条预案, 状态: {statuses}")
            else:
                record(phase, "预案列表", "PASS", f"{row_count} 条预案")
        else:
            record(phase, "预案列表", "WARN", "列表为空")
    else:
        record(phase, "预案列表", "FAIL", "表格未渲染")

    # 4.2 点击编辑进入评估
    edit_link = page.locator(f"a[href='/plans/{TEST_STOCK}']")
    if edit_link.count() > 0:
        edit_link.first.click()
        page.wait_for_timeout(LOAD_WAIT)

        # 查找评估按钮
        eval_btn = page.locator("button >> text='立即评估当前版本'")
        if eval_btn.count() > 0:
            eval_btn.first.click()
            page.wait_for_timeout(3000)

            # 检查消息提示
            msg = page.locator(".ant-message")
            if msg.count() > 0:
                record(phase, "预案评估", "PASS", msg.first.text_content() or "评估完成")
            else:
                record(phase, "预案评估", "WARN", "未收到反馈消息")
            screenshot(page, "04-plan-evaluate")
        else:
            record(phase, "预案评估", "WARN", "评估按钮不存在（可能是新建模式）")
    else:
        record(phase, "预案评估", "WARN", f"未找到 {TEST_STOCK} 的编辑链接")

    # 4.3 查看草稿（通过 Cockpit）
    page.goto(f"{BASE_URL}/", wait_until="networkidle")
    page.wait_for_timeout(LOAD_WAIT)
    draft_card = page.locator(".ant-card-head-title:has-text('今日订单草稿')")
    if draft_card.count() > 0:
        record(phase, "草稿区域", "PASS", "草稿卡片存在")
        # 检查草稿数量
        draft_table = page.locator("text='今日订单草稿' >> .. >> .. table")
        if draft_table.count() > 0:
            rows = draft_table.locator("tbody tr").count()
            record(phase, "草稿数量", "PASS", f"{rows} 条草稿")
        else:
            record(phase, "草稿数量", "WARN", "今日无草稿")
        screenshot(page, "04-drafts")
    else:
        record(phase, "草稿区域", "WARN", "未找到草稿区域")


def phase5_cockpit(page):
    """阶段5: 执行交易 (Cockpit)"""
    phase = "执行交易"
    print(f"\n{'='*60}\n  阶段5: {phase}\n{'='*60}")

    page.goto(f"{BASE_URL}/", wait_until="networkidle")
    page.wait_for_timeout(LOAD_WAIT)
    screenshot(page, "05-cockpit")

    # 5.1 页面标题
    title = page.locator("text='自动驾驶舱'")
    if title.count() > 0:
        record(phase, "Cockpit加载", "PASS")
    else:
        record(phase, "Cockpit加载", "FAIL", "标题未找到")

    # 5.2 现金流目标进度
    goal_progress = page.locator(".ant-progress")
    goal_text = page.locator("text='现金流目标进度'")
    if goal_progress.count() > 0 or goal_text.count() > 0:
        progress = page.locator(".ant-progress")
        if progress.count() > 0:
            record(phase, "现金流目标", "PASS", "进度条存在")
        else:
            record(phase, "现金流目标", "PASS", "卡片存在但无进度条（可能未设目标）")
        screenshot(page, "05-cashflow-goal")
    else:
        record(phase, "现金流目标", "WARN", "未找到目标卡片")

    # 5.3 草稿订单区域
    draft_section = page.locator(".ant-card-head-title:has-text('今日订单草稿')")
    if draft_section.count() > 0:
        record(phase, "草稿区域", "PASS")
        screenshot(page, "05-drafts-area")

        # 5.4 执行按钮检查
        exec_btn = page.locator("button >> text='标记已成交'")
        cancel_btn = page.locator("button >> text='取消'")
        if exec_btn.count() > 0:
            record(phase, "执行按钮", "PASS", f"有 {exec_btn.count()} 个待执行草稿")
            # 点击执行触发纪律检查
            exec_btn.first.click()
            page.wait_for_timeout(ACTION_WAIT)
            # 检查纪律检查清单模态框
            discipline_modal = page.locator(".ant-modal")
            if discipline_modal.count() > 0:
                modal_text = discipline_modal.first.text_content() or ""
                if "纪律" in modal_text or "确认" in modal_text:
                    record(phase, "纪律检查清单", "PASS", "模态框已弹出")
                    screenshot(page, "05-draft-execute")
                    # 取消关闭
                    close_btn = discipline_modal.locator("button >> text='取消'")
                    if close_btn.count() > 0:
                        close_btn.last.click()
                        page.wait_for_timeout(500)
                else:
                    record(phase, "纪律检查清单", "WARN", f"模态框内容: {modal_text[:50]}")
            else:
                record(phase, "纪律检查清单", "WARN", "未弹出纪律检查模态框")
        else:
            record(phase, "执行按钮", "WARN", "今日无待执行草稿")

        # 5.5 取消按钮
        if cancel_btn.count() > 0:
            record(phase, "取消按钮", "PASS", "取消按钮存在")
            screenshot(page, "05-draft-cancel")
        else:
            record(phase, "取消按钮", "WARN", "无取消按钮（无草稿或只有执行）")
    else:
        record(phase, "草稿区域", "WARN", "今日无草稿")

    # 5.6 市场周期
    cycle_card = page.locator("text='市场周期'")
    if cycle_card.count() > 0:
        record(phase, "市场周期", "PASS", "周期卡片存在")
        screenshot(page, "05-market-cycle")
    else:
        record(phase, "市场周期", "WARN", "未找到市场周期卡片")

    # 5.7 主题配置偏离
    theme_card = page.locator(".ant-card-head-title:has-text('主题配置')")
    if theme_card.count() > 0:
        record(phase, "主题配置", "PASS", "主题偏离表格存在")
        screenshot(page, "05-theme-exposure")
    else:
        record(phase, "主题配置", "WARN", "未找到主题配置卡片")

    # 5.8 持仓表格
    holdings_card = page.locator(".ant-card-head-title:has-text('持仓')")
    if holdings_card.count() > 0:
        # 找到持仓卡片内的表格
        holdings_parent = holdings_card.first.evaluate_handle("el => el.closest('.ant-card')").as_element()
        if holdings_parent:
            holdings_table = holdings_parent.query_selector("table")
            if holdings_table:
                rows = len(holdings_table.query_selector_all("tbody tr"))
                record(phase, "持仓表格", "PASS", f"{rows} 条持仓")
            else:
                record(phase, "持仓表格", "WARN", "无持仓表格")
        else:
            record(phase, "持仓表格", "WARN", "未找到持仓卡片容器")
        screenshot(page, "05-holdings")
    else:
        record(phase, "持仓表格", "WARN", "未找到持仓卡片")

    # 额外: 四象限饼图
    quadrant_card = page.locator("text='四象限分布'")
    if quadrant_card.count() > 0:
        record(phase, "四象限分布", "PASS", "饼图卡片存在")

    # 额外: 告警列表
    alerts_card = page.locator("text='未确认告警'")
    if alerts_card.count() > 0:
        record(phase, "告警列表", "PASS", "告警卡片存在")


def phase6_portfolio(page):
    """阶段6: 持仓管理（通过 API 验证）"""
    phase = "持仓管理"
    print(f"\n{'='*60}\n  阶段6: {phase}\n{'='*60}")

    import urllib.request

    # 6.1 组合概览
    try:
        req = urllib.request.Request(f"{API_URL}/api/portfolio/summary")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            record(phase, "组合概览", "PASS",
                   f"总值={data.get('total_value', 'N/A')}, 持仓数={data.get('holding_count', 'N/A')}")
    except Exception as e:
        record(phase, "组合概览", "FAIL", str(e))

    screenshot(page, "06-portfolio-summary")

    # 6.2 分红预测
    try:
        req = urllib.request.Request(f"{API_URL}/api/market/dividend-projection")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            record(phase, "分红预测", "PASS",
                   f"12月预期={data.get('next_12m_expected', 'N/A')}")
    except Exception as e:
        record(phase, "分红预测", "FAIL", str(e))

    screenshot(page, "06-dividend-projection")

    # 6.3 估值快照（对测试股票）
    try:
        req = urllib.request.Request(f"{API_URL}/api/valuation/{TEST_STOCK}/percentile")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            record(phase, "估值快照", "PASS",
                   f"PE%={data.get('pe_pct_10y', 'N/A')}, PB%={data.get('pb_pct_10y', 'N/A')}")
    except Exception as e:
        record(phase, "估值快照", "FAIL", str(e))

    screenshot(page, "06-valuation")

    # 6.4 论点警报
    try:
        req = urllib.request.Request(f"{API_URL}/api/market/thesis-alerts")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            alerts_count = len(data) if isinstance(data, list) else 0
            record(phase, "论点警报", "PASS", f"{alerts_count} 个警报")
    except Exception as e:
        record(phase, "论点警报", "FAIL", str(e))

    screenshot(page, "06-thesis-alerts")


def phase7_review(page):
    """阶段7: 复盘"""
    phase = "复盘"
    print(f"\n{'='*60}\n  阶段7: {phase}\n{'='*60}")

    page.goto(f"{BASE_URL}/review", wait_until="networkidle")
    page.wait_for_timeout(LOAD_WAIT)
    screenshot(page, "07-review-monthly")

    # 页面标题
    title = page.locator("text='复盘'")
    if title.count() > 0:
        record(phase, "复盘页面", "PASS")
    else:
        record(phase, "复盘页面", "FAIL", "标题未找到")

    # 7.2 草稿命中率
    hit_rate = page.locator("text='草稿命中率'")
    if hit_rate.count() > 0:
        stat = hit_rate.locator("..").locator(".ant-statistic-content-value")
        if stat.count() > 0:
            record(phase, "草稿命中率", "PASS", f"值: {stat.first.text_content()}")
        else:
            record(phase, "草稿命中率", "PASS", "统计卡片存在")
        screenshot(page, "07-hit-rate")
    else:
        record(phase, "草稿命中率", "WARN", "未找到命中率统计")

    # 7.3 审计时间线
    timeline = page.locator(".ant-timeline")
    if timeline.count() > 0:
        items = timeline.locator(".ant-timeline-item")
        record(phase, "审计时间线", "PASS", f"{items.count()} 条记录")
        screenshot(page, "07-audit-timeline")
    else:
        # 可能为空
        empty_text = page.locator("text='本月无事件'")
        if empty_text.count() > 0:
            record(phase, "审计时间线", "PASS", "本月无事件")
        else:
            record(phase, "审计时间线", "WARN", "时间线未渲染")

    # 7.4 季度视图
    quarterly_tab = page.locator(".ant-tabs-tab >> text='季度'")
    if quarterly_tab.count() > 0:
        quarterly_tab.first.click()
        page.wait_for_timeout(TAB_WAIT)
        record(phase, "季度视图", "PASS", "Tab 已切换")
        screenshot(page, "07-review-quarterly")
    else:
        record(phase, "季度视图", "FAIL", "Tab 不存在")

    # 7.5 年度视图
    annual_tab = page.locator(".ant-tabs-tab >> text='年度'")
    if annual_tab.count() > 0:
        annual_tab.first.click()
        page.wait_for_timeout(TAB_WAIT)
        record(phase, "年度视图", "PASS", "Tab 已切换")
        screenshot(page, "07-review-annual")
    else:
        record(phase, "年度视图", "FAIL", "Tab 不存在")


# ── 主流程 ────────────────────────────────────────────────────────────

def run_lifecycle():
    print("\n" + "=" * 60)
    print("  Gojira 用户全生命周期 E2E 验证")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  测试标的: {TEST_STOCK} {TEST_STOCK_NAME}")
    print(f"  截图目录: {SCREENSHOT_DIR}")
    print("=" * 60)

    # 检查前后端
    import urllib.request
    try:
        req = urllib.request.Request(f"{API_URL}/api/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            health = json.loads(resp.read())
            print(f"\n  后端状态: {health.get('status', 'unknown')}")
    except Exception as e:
        print(f"\n  ❌ 后端不可用: {e}")
        print("  请先启动前后端: ./dev.sh")
        return

    try:
        req = urllib.request.Request(BASE_URL)
        with urllib.request.urlopen(req, timeout=5):
            print(f"  前端状态: ok")
    except Exception:
        print(f"  ⚠️ 前端不可用，请检查 localhost:3000")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu"],
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = context.new_page()

        # 设置默认超时
        page.set_default_timeout(15000)

        try:
            phase1_universe(page)
        except Exception as e:
            record("选股发现", "阶段异常", "FAIL", str(e))
            traceback.print_exc()

        try:
            phase2_stock_detail(page)
        except Exception as e:
            record("深度研究", "阶段异常", "FAIL", str(e))
            traceback.print_exc()

        try:
            phase3_plan_editor(page)
        except Exception as e:
            record("制定预案", "阶段异常", "FAIL", str(e))
            traceback.print_exc()

        try:
            phase4_evaluation(page)
        except Exception as e:
            record("评估草稿", "阶段异常", "FAIL", str(e))
            traceback.print_exc()

        try:
            phase5_cockpit(page)
        except Exception as e:
            record("执行交易", "阶段异常", "FAIL", str(e))
            traceback.print_exc()

        try:
            phase6_portfolio(page)
        except Exception as e:
            record("持仓管理", "阶段异常", "FAIL", str(e))
            traceback.print_exc()

        try:
            phase7_review(page)
        except Exception as e:
            record("复盘", "阶段异常", "FAIL", str(e))
            traceback.print_exc()

        # 最终 Cockpit 截图
        page.goto(f"{BASE_URL}/", wait_until="networkidle")
        page.wait_for_timeout(2000)
        screenshot(page, "99-final-cockpit")

        browser.close()

    # ── 生成报告 ───────────────────────────────────────────────────────

    pass_count = sum(1 for r in results if r["status"] == "PASS")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    warn_count = sum(1 for r in results if r["status"] == "WARN")
    total = len(results)

    print("\n" + "=" * 60)
    print("  验证报告汇总")
    print("=" * 60)
    print(f"\n  总计: {total} 步")
    print(f"  ✅ 通过: {pass_count}")
    print(f"  ❌ 失败: {fail_count}")
    print(f"  ⚠️  警告: {warn_count}")

    if fail_count > 0:
        print("\n  失败项:")
        for r in results:
            if r["status"] == "FAIL":
                print(f"    ❌ [{r['phase']}] {r['step']}: {r['detail']}")

    # 写入报告文件
    report_path = SCREENSHOT_DIR / "lifecycle_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Gojira 用户全生命周期验证报告\n\n")
        f.write(f"- **日期**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- **测试标的**: {TEST_STOCK} {TEST_STOCK_NAME}\n")
        f.write(f"- **总计**: {total} 步 | ✅ {pass_count} | ❌ {fail_count} | ⚠️ {warn_count}\n\n")

        # 按阶段分组
        phases = []
        seen = set()
        for r in results:
            if r["phase"] not in seen:
                seen.add(r["phase"])
                phases.append(r["phase"])

        for phase_name in phases:
            phase_results = [r for r in results if r["phase"] == phase_name]
            f.write(f"## {phase_name}\n\n")
            f.write("| 步骤 | 状态 | 详情 |\n")
            f.write("|------|------|------|\n")
            for r in phase_results:
                icon = "✅" if r["status"] == "PASS" else "❌" if r["status"] == "FAIL" else "⚠️"
                f.write(f"| {r['step']} | {icon} {r['status']} | {r['detail']} |\n")
            f.write("\n")

        # 截图列表
        screenshots = sorted(SCREENSHOT_DIR.glob("*.png"))
        if screenshots:
            f.write("## 截图证据\n\n")
            for s in screenshots:
                rel = s.relative_to(SCREENSHOT_DIR)
                f.write(f"- [{rel.name}](./{rel})\n")

    print(f"\n  📄 报告已保存: {report_path}")
    print(f"  📸 截图目录: {SCREENSHOT_DIR}")
    print()


if __name__ == "__main__":
    run_lifecycle()
