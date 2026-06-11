# Lixinger API 接口审计报告

> 审计日期：2026-06-05
> 修复日期：2026-06-05
> 审计范围：`backend/app/services/lixinger_client.py` 全部 15 个 API 方法，对照 `.claude/skills/lixinger/api-docs/` 官方文档

## 审计方法

逐一将代码中的每个方法与其对应的 Lixinger API 文档比对，检查：
1. 请求参数名称和类型（单数/复数、String/Array）
2. 必填参数是否全部传递
3. 指标格式是否符合 API 定义的层级规则
4. 调用方（market_service 等）使用的端点是否正确

---

## 修复总览

| 编号 | 问题 | 优先级 | 状态 |
|------|------|--------|------|
| L-01 | 银行基本面缺少 date | P0 | **已修复** |
| L-02 | 行业基本面默认指标格式错误 | P0 | **已修复** |
| L-03 | 指数基本面默认指标格式错误 | P0 | **已修复** |
| L-04 | 6 个端点 stockCodes → stockCode | P1 | **已修复** |
| L-05 | 6 个端点缺少必填 startDate | P1 | **已修复** |
| L-06 | K线缺少必填 type 参数 | P1 | **已修复** |
| L-07 | 资金流使用错误端点 | P1 | **已修复** |
| L-08 | 行业基本面 stockCodes 非必填 | P2 | **已修复** |
| L-09 | company list 使用未文档化 pageSize | P2 | 已确认（API 接受，保留） |
| L-10 | 响应字段名可能不匹配 | P2 | **已修复**（L-07 中的 netBuyAmount） |

---

## 修复详情

### L-01: `get_fundamentals_for_bank` 缺少必填 date/startDate ✅

添加 `start_date`/`end_date` 参数，并在无 date 时默认使用当天日期。

### L-02: `get_industry_fundamental` 默认指标格式错误 ✅

默认 metrics 从 `["pe_ttm", "pb", "dyr"]` 改为 `["pe_ttm.mcw", "pb.mcw", "dyr.mcw"]`。
同时将 `date: "latest"` 改为 `datetime.now().strftime("%Y-%m-%d")`。

### L-03: `get_index_fundamental` 默认指标格式错误 ✅

默认 metrics 从 `["pe_ttm", "pb", "dyr", "mc"]` 改为 `["pe_ttm.mcw", "pb.mcw", "dyr.mcw", "mc"]`。

### L-04+L-05+L-06: 6 个端点参数修复 ✅

统一修复：
- `get_kline`: `stockCode` + 必填 `start_date` + 必填 `type`（默认 `lxr_fc_rights`）
- `get_index_kline`: `stockCode` + 必填 `start_date` + 必填 `type`（默认 `normal`）
- `get_dividend`: `stockCode` + 必填 `start_date`
- `get_majority_shareholders`: `stockCode` + 必填 `start_date`
- `get_mutual_market`: `stockCode` + 必填 `start_date`
- `get_margin_trading`: `stockCode` + 必填 `start_date`

### L-07: 资金流端点修复 ✅

- 新增 `get_index_mutual_market` 方法，使用 `/cn/index/mutual-market`
- `market_service.fetch_capital_flow` 改用新方法
- 响应字段从 `mm_nba` 改为 `netBuyAmount`

### L-08: 行业基本面 stockCodes 必填 ✅

`stock_codes` 参数从 `Optional[list[str]] = None` 改为 `list[str]`（必填）。

### L-10: 响应字段名修正 ✅

`fetch_capital_flow` 中 `mm_nba` → `netBuyAmount`。

---

## 无问题的接口

| 方法 | API 路径 | 状态 |
|------|---------|------|
| `get_company_list` | `/cn/company` | 正确 |
| `get_company_profile` | `/cn/company/profile` | 正确 |
| `get_fundamentals` | `/cn/company/fundamental/non_financial` | 正确 |
| `get_financials` | `/cn/company/fs/non_financial` | 正确 |
| `get_industry_list` | `/cn/industry` | 正确 |
| `get_industry_constituents` | `/cn/industry/constituents/sw_2021` | 正确 |

---

## 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `backend/app/services/lixinger_client.py` | 修复 10 个方法的参数签名和 payload 构造 |
| `backend/app/services/market_service.py` | 资金流改用指数互联互通端点 + 字段映射修正 |
