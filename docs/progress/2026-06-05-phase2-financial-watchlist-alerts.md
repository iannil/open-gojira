# 2026-06-05 阶段 2 实施进展：TTM 财务 + 财务柱图 + 自选阈值闭环 + 预警规则扩展

## 背景

源自 `~/.claude/plans/lixinger-compressed-pascal.md` 阶段 2（P1）。阶段 1 完成后，本阶段补齐研究深度（TTM、趋势可视化）与预警闭环（自选触发、4 类新规则）。

## 完成项

### 2.1 TTM 财务汇总 ✅
- 文件：`backend/app/services/financial_service.py`、`tests/test_ttm.py`
- `get_ratio_trends` 季度分支现在返回 **TTM 滚动数据**：对最近 4 季 `revenue/net_profit` 求和；季度增长率改为 TTM YoY（当前 TTM / 前一年 TTM − 1）
- 抽出 `compute_ttm_series()` 纯函数，便于复用与测试
- 新增 2 个回归测试（含 8 季度合成数据验证 TTM 数值与缺数据降级）

### 2.2 财务趋势柱图 ✅
- 文件：`frontend/src/components/financial/RevenueProfitBarChart.tsx`、`pages/FinancialPage.tsx`
- 在「三大表」Tab 顶部插入 ECharts 组合图：营收 / 净利 / 经营现金流 三柱 + 毛利率折线（双 Y 轴），单位自动转亿元；时间倒序输入自动反转

### 2.3 自选阈值闭环 ✅
后端：
- `alert_service.sync_rules_from_watchlist()`：对每个 `WatchlistItem` 的 `target_pe_pct / target_pb_pct` 自动维护对应 `pe_percentile_cross / pb_percentile_cross` 规则；用 `note=[auto-watchlist]` 标识区分用户手动规则
- `watchlist_service.update_item` 与 `remove_item` 调用 `_sync_auto_rules` 自动收敛
- 新路由 `POST /api/alerts/rules/sync-from-watchlist` 手动触发
- `update_item` 改为 sentinel-aware（允许 null 清空阈值）

前端：
- `api/client.ts` 新增 `updateWatchlistItem`
- 新组件 `components/watchlist/ThresholdEditModal.tsx`
- `WatchlistPanel` 表格"操作"列加「阈值」入口；模态保存后自动 reload

测试：`tests/test_alert_autosync.py` 3 用例（首次创建、更新+清空、保护用户规则）

### 2.4 预警规则扩展 ✅
- 文件：`backend/app/schemas/alert.py`、`backend/app/services/alert_service.py`、`tests/test_alert_new_rules.py`、`frontend/src/api/types.ts`、`pages/AlertsPage.tsx`
- 4 类新规则：
  - **price_cross**: params `{direction: "below"|"above", price}` — 价格穿越绝对值
  - **dyr_cross**: params `{threshold_pct}` — 股息率到达地板（"股息地板 5%"）
  - **dividend_ex_date_near**: params `{days_ahead}` — 本地 `DividendRecord.ex_date` 在 N 天内
  - **financial_report_released**: 无参 — 自 `last_evaluated_at` 后新增 FinancialStatement 行触发
- `RULE_TYPES` 元组扩展为 8 项
- AlertsPage：`RULE_LABELS` 扩充；新建规则模态按规则类型动态渲染表单字段（方向/目标价、股息阈值、提前天数等）
- 测试：5 个回归用例覆盖每个新规则

## 验证

- 后端：`pytest tests/ -q` → **184 passed**（阶段 1 后 174 + TTM 2 + autosync 3 + new_rules 5）
- 前端：`npm run build` 通过
- 前端 lint：维持存量水平（无新增违规类别）

## 关键文件

```
backend:
  app/services/financial_service.py        修改（compute_ttm_series + 季度 TTM）
  app/services/alert_service.py            修改（sync_rules_from_watchlist + 4 个新 _eval_*）
  app/services/watchlist_service.py        修改（update/remove 触发自动同步；null sentinel）
  app/schemas/alert.py                     修改（RULE_TYPES 扩展）
  app/routers/alerts.py                    修改（/sync-from-watchlist 端点）
  tests/test_ttm.py                        新增
  tests/test_alert_autosync.py             新增
  tests/test_alert_new_rules.py            新增

frontend:
  src/components/financial/RevenueProfitBarChart.tsx  新增
  src/components/watchlist/ThresholdEditModal.tsx     新增
  src/components/watchlist/WatchlistPanel.tsx         修改（阈值入口）
  src/pages/FinancialPage.tsx                         修改（嵌入柱图）
  src/pages/AlertsPage.tsx                            修改（4 类新规则表单）
  src/api/client.ts                                   修改（updateWatchlistItem）
  src/api/types.ts                                    修改（AlertRuleType 扩展）
```

## 未做（明确）

- 阶段 2 完整完成。
- 后续阶段 3（Dashboard 死链、命令面板、抽离硬编码阈值、前瞻分红日历、Compare 时序）与阶段 4（K 线缓存、`merge` 重复、并发锁、ECharts tree-shaking）尚未启动。
