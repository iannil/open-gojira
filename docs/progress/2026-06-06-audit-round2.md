# 审计报告 — 2026-06-06

> 继 2026-06-05 首次审计（30项问题，23项修复，7项延期）后的第二轮审计。

## 审计范围

1. 复查7项延期问题的当前状态
2. 审查新增代码质量（theme / dividend sustainability / market temperature / rebalance / thesis variables）
3. 架构一致性、安全性、可观测性合规性检查

## 发现与修复

### Critical（已修复）

| # | 问题 | 文件 | 修复 |
|---|------|------|------|
| C-1 | Theme 路由 `prefix="/themes"` 缺少 `/api/`，Vite 代理无法转发 | `routers/theme.py:17` | 改为 `/api/themes` |
| C-2 | `theme_service.get_theme_exposure()` 用股数代替市值，权重计算错误 | `services/theme_service.py:53` | 引入 `_get_cached_price` 计算真实市值 |

### High（已修复）

| # | 问题 | 文件 | 修复 |
|---|------|------|------|
| H-1 | Cockpit 每次 GET 触发再平衡全量计算（3-4个重量级服务） | `services/cockpit_service.py:153` | 添加 1h TTL 缓存 |
| H-2 | `get_portfolio_summary` 中 `_latest_dyr` 逐持仓查询（N+1） | `services/holding_service.py:399` | 新增 `_batch_latest_dyrs` 批量查询 |
| H-3 | 可观测性模块零采用（CLAUDE.md 合规性） | 全部27个 service 文件 | cockpit_service + plan_runner 迁移到 `get_logger` / `track_lifecycle` |

### Medium（已修复）

| # | 问题 | 文件 | 修复 |
|---|------|------|------|
| M-1 | `market_temperature_service` 全局缓存无锁 | `services/market_temperature_service.py` | 添加 `threading.Lock` |
| M-2 | Theme schema 定义在 router 内 | `routers/theme.py:20-37` | 提取到 `schemas/theme.py` |
| M-3 | Theme CRUD 无输入校验 | `routers/theme.py` | `Field(min_length=1, max_length=50, ge=0, le=100)` |
| M-4 | Theme 路由异常信息泄露 | `routers/theme.py:61` | 返回通用错误信息 |
| M-5 | Cockpit aggregator 无测试 | 缺少测试文件 | 新建 `test_cockpit_aggregator.py`（7项） |
| M-6 | 前端3个 API 函数返回 `Promise<unknown>` | `frontend/src/api/client.ts` | 添加泛型类型参数 |

### Low（记录/接受）

| # | 问题 | 位置 |
|---|------|------|
| L-1 | Cockpit 页面独立发起2次 API 调用 | `CockpitPage.tsx:879` |
| L-2 | ORM-response 转换仍在部分路由散落 | `stocks.py`, `plans.py` |
| L-3 | 部分业务阈值未集中到 `constants.py` | `theme_service.py`, `rebalance_service.py` |
| L-4 | 迁移降级在 SQLite 上静默跳过列删除 | `alembic/versions/l2g3h4i5j6k7` |
| L-5 | 无 CI/CD、无 Python lint/type-check | 项目根目录 |

### 延期项状态

| 延期项 | 新状态 |
|--------|--------|
| 全局单例锁 | 未解决（LixingerClient 已有锁，market_temperature 已加锁） |
| 前端重复请求 | L-1 接受 |
| Service Schema 耦合 | 未解决（5个 service 仍导入 schemas） |
| ORM Response 散落 | L-2 接受 |
| N+1 查询 | **H-2 已修复**（DYR 批量查询） |
| ECharts 打包 | **已修复**（按需导入） |
| 硬编码阈值 | 大部分修复（`constants.py` + 少量散落 L-3） |

## 修改文件清单

| 文件 | 变更 |
|------|------|
| `backend/app/routers/theme.py` | 修复前缀、导入提取的 schema、修复异常信息 |
| `backend/app/schemas/theme.py` | **新建** — 从 router 提取的 schema + 输入校验 |
| `backend/app/services/theme_service.py` | 修复市值计算（引入 `_get_cached_price`） |
| `backend/app/services/cockpit_service.py` | 再平衡缓存 + 迁移到 `get_logger` / `track_lifecycle` |
| `backend/app/services/holding_service.py` | 新增 `_batch_latest_dyrs` 批量查询 |
| `backend/app/services/market_temperature_service.py` | 添加线程锁 |
| `backend/app/services/plan_runner.py` | 迁移到 `get_logger` / `track_lifecycle` |
| `frontend/src/api/client.ts` | 3个函数添加泛型类型 |
| `frontend/src/api/types.ts` | ThemeExposure/ThemeItem 导出（已有） |
| `frontend/src/pages/CockpitPage.tsx` | 移除 `as ThemeExposure` 类型断言 |
| `backend/tests/test_cockpit_aggregator.py` | **新建** — 7项测试 |

## 验证结果

```
pytest → 304 passed (从 297 增加)
frontend: npm run build → ✓
```
