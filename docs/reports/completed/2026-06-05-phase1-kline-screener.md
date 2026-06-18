# 2026-06-05 阶段 1 实施进展：K 线 + 估值带 + 筛选器修复

## 背景

源自 `~/.claude/plans/lixinger-compressed-pascal.md`（"Gojira 个人投资分析平台业务完整度审计与改进路线图"）阶段 1（P0），目的：消除阻塞日常使用的三大短板。

## 完成项

### 1.2 筛选器蓝筹批量 API 修复 ✅
- 文件：`backend/app/services/screener_service.py`、`backend/app/schemas/screener.py`、`backend/tests/test_screener_b2.py`
- 改动：
  - 重写批量后的 fallback 逻辑：除了"完全缺失"的 code，也对**任一关键指标为 None** 的 code 触发单股 fallback；命中越多越好的指标才替换原值。
  - `ScreenerRunResponse` 增加 `diagnostics`：`universe_size / batch_failures / fallback_attempted / fallback_recovered / missing_after_fallback`，可用于前端诊断长江电力类蓝筹被捞回的次数。
- 测试：新增 `test_run_screener_fallback_recovers_blue_chip_with_none_metrics`。

### 1.3 财务字段筛选 + Peer 修复 ✅
- 文件：`backend/app/services/screener_service.py`、`backend/app/services/financial_service.py`、`backend/tests/test_screener_b2.py`
- 新增 8 个本地财务筛选字段（基于最新年报）：`roe / roa / gross_margin / net_margin / revenue_growth / net_profit_growth / debt_ratio / ocf_to_profit_ratio`。
- 实现方式：当激活财务筛选时，单条 SQL 子查询取每个 stock_code 最近一笔 annual 报告并批量 join，避免 N+1。
- Peer comparison 修 2 个 bug：
  - 原代码用 `companies = client.get_company_list(page=0, page_size=1)` 后未使用，名字始终是 code。改为优先从本地 `Stock` 表反查，再回退到 industry constituents 中的 name 字段。
  - 删除了被遗忘的 `page_size=1` 调用。

### 1.1 K 线 + 估值带集成 ✅
后端：
- 新建 `app/models/price_kline.py`（PriceKline 表）+ 注册到 `models/__init__.py`，由启动时 `Base.metadata.create_all()` 自动建表。
- 新建 `app/services/kline_service.py`：增量拉取 + DB 缓存，`get_klines()` 自动按"上一次缓存日 −5 天 → 今天"补差；`get_valuation_bands()` 在 P10/P50/P90 历史分位上输出"价格 × 估值带"序列（implied_close = close × band_multiple / actual_multiple）。
- 新建 `app/schemas/kline.py`，扩展 `app/routers/stocks.py`：
  - `GET /api/stocks/{code}/kline?days=&freq=`
  - `GET /api/stocks/{code}/valuation-bands?metric=pe_ttm|pb&years=`
- 测试：新建 `tests/test_kline_service.py`（2 用例，验证缓存与估值带组装）。

前端：
- `frontend/src/lib/echarts.ts` 注册 `CandlestickChart`。
- `frontend/src/api/types.ts` + `client.ts` 增加 `KlinePoint / KlineResponse / ValuationBandsResponse / BandLevel` 类型及 `fetchKline / fetchValuationBands`。
- 新增组件：
  - `components/stock/KlineChart.tsx`：日 K 蜡烛图 + MA5/20/60 + 成交量子图 + 3M/6M/1Y/3Y/5Y 切换 + dataZoom。
  - `components/valuation/PriceWithBandsChart.tsx`：收盘价 + P10/P50/P90 估值带叠加；可切 PE/PB 与 3Y/5Y/10Y。
- 集成：
  - `pages/StockDetailPage.tsx` 新增首位 `K线` Tab。
  - `pages/ValuationPage.tsx` 新增 `价格 × 估值带` Tab（位于 PE/PB 分位与股息之间）。

## 验证

- 后端：`pytest tests/ -q` → **174 passed**（原 172 + kline_service 2）
- 前端：`npm run build` 通过；新组件未引入新增 TS 错误。
- 前端 lint：项目存量 22 个 `react-hooks/set-state-in-effect` 错误，新组件沿用相同 useEffect+setLoading 模式（与 `StockDetailPage`、`ScreenerPage` 等已有页面一致），未引入新的违规类别。

## 仍未做（明确）

- 阶段 1 范围内已全部完成；后续阶段 2/3/4 仍待启动（见路线图）。
- 自选阈值闭环、TTM 财务、预警规则扩展、Dashboard 死链修复等属于阶段 2/3。

## 关键文件

```
backend/app/models/price_kline.py                       新增
backend/app/services/kline_service.py                   新增
backend/app/schemas/kline.py                            新增
backend/app/services/screener_service.py                修改（fallback + financial 字段）
backend/app/services/financial_service.py               修改（peer name 修复）
backend/app/schemas/screener.py                         修改（diagnostics 字段）
backend/app/routers/stocks.py                           修改（kline + bands 路由）
backend/app/models/__init__.py                          修改（注册 PriceKline）
backend/tests/test_screener_b2.py                       新增 2 用例
backend/tests/test_kline_service.py                     新增

frontend/src/lib/echarts.ts                             修改（CandlestickChart）
frontend/src/api/types.ts                               修改（Kline/Bands 类型）
frontend/src/api/client.ts                              修改（fetchKline/Bands）
frontend/src/components/stock/KlineChart.tsx            新增
frontend/src/components/valuation/PriceWithBandsChart.tsx 新增
frontend/src/pages/StockDetailPage.tsx                  修改（K线 Tab）
frontend/src/pages/ValuationPage.tsx                    修改（估值带 Tab）
```
