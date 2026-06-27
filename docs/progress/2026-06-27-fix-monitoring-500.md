# Fix: Monitoring 页面 500 错误

**时间**: 2026-06-27 18:55 CST

## 问题

`http://localhost:7149/monitoring` 页面两个 metrics 端点返回 500：

- `GET /api/metrics/pipelines?days=30` → 500 Internal Server Error
- `GET /api/metrics/llm?days=30` → 500 Internal Server Error

`GET /api/metrics/llm/trend?days=30` 和 `GET /api/system-alerts` 正常工作。

## 根因

`app/services/metrics_service.py` 中使用了 SQLite 特有的函数，在 PostgreSQL 数据库中不存在：

1. **`func.unixepoch()`** — `get_pipeline_summary()` 第 86 行，用于计算 pipeline 执行平均耗时
   - PostgreSQL 错误: `function unixepoch(timestamp without time zone) does not exist`

2. **`func.json_type()`** — `get_llm_summary()` 第 182 行和第 211 行，用于检查 `conflict_flags_json` 是否为有效 JSON
   - PostgreSQL 错误: `function json_type(json) does not exist`
   - 在 PostgreSQL 中 JSON 列类型已保证存储内容为有效 JSON，`IS NOT NULL` 检查已足够

## 修复

### 文件: `backend/app/services/metrics_service.py`

| 位置 | 修改前 (SQLite) | 修改后 (PostgreSQL) |
|------|-----------------|---------------------|
| `get_pipeline_summary` duration 计算 | `func.unixepoch(finished_at) - func.unixepoch(started_at)` | `func.extract('epoch', finished_at) - func.extract('epoch', started_at)` |
| `get_llm_summary` 冲突率查询 (2处) | `func.json_type(col).isnot(None)` | 移除该行，仅保留 `col.isnot(None)` |

## 验证

```bash
# 修复前
$ curl http://localhost:7149/api/metrics/pipelines?days=30
{"detail":"Internal server error"}  # 500

$ curl http://localhost:7149/api/metrics/llm?days=30
{"detail":"Internal server error"}  # 500

# 修复后
$ curl http://localhost:7149/api/metrics/pipelines?days=30
{"period_days":30,"pipelines":{},"overall":{"total":0,"success_rate_pct":0.0}}  # 200

$ curl http://localhost:7149/api/metrics/llm?days=30
{"total_calls":180,"total_cost_usd":1.0995,"success_rate_pct":100.0,...}  # 200
```
