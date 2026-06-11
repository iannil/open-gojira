# 代码审计发现

> 审计日期：2026-06-04（初次）、2026-06-05（复审）、2026-06-05（全面审计）

## 全面审计状态（2026-06-05）

共发现 30 项审计问题，按 7 个维度分类。已完成修复 20 项，剩余 10 项为 P2/P3 优先级。

### 已修复项

| # | 编号 | 问题 | 修复措施 | 日期 |
|---|------|------|---------|------|
| 1 | — | holding_service 同步网络调用循环 | 添加缓存+错误日志 | 2026-06-05 |
| 2 | — | 分红年度收益率计算错误 | 改用 TTM | 2026-06-05 |
| 3 | — | _snapshot_to_response 重复定义 | 统一定义 | 2026-06-05 |
| 4 | — | CheckWizard maxScore 硬编码 25 | 动态计算 | 2026-06-05 |
| 5 | — | valuation.py 行内 import | 移至顶部 | 2026-06-05 |
| 6 | — | DisciplineCheck.score 无校验边界 | ge=0, le=20 | 2026-06-05 |
| 7 | — | frontend/README.md 是 Vite 模板默认内容 | 已更新 | 2026-06-05 |
| 8 | — | backend/data/imports/ 未版本控制 | .gitkeep | 2026-06-05 |
| 9 | — | TypeScript 构建失败（7 个错误） | 已修复 | 2026-06-05 |
| 10 | A-01 | SQLite 无 WAL 模式，并发写入可能锁死 | 启用 WAL + busy_timeout + foreign_keys | 2026-06-05 |
| 11 | S-02 | CORS allow_methods/headers 过于宽松 | 限制为明确列表 | 2026-06-05 |
| 12 | S-03 | 文件上传无类型/大小验证 | .csv 白名单 + 10MB 限制 | 2026-06-05 |
| 13 | S-06 | 缺少 .env.example，Token 无启动验证 | 创建 .env.example，添加启动警告 | 2026-06-05 |
| 14 | C-01 | 依赖版本未固定 | requirements.txt 锁定版本 | 2026-06-05 |
| 15 | O-03 | 健康检查无深度探针 | 添加 DB 连接和 Token 检查 | 2026-06-05 |
| 16 | O-01 | 缺少结构化日志（CLAUDE.md 要求） | 创建 observability 模块 + structlog | 2026-06-05 |
| 17 | O-02 | 无请求追踪/关联 ID | 添加 trace_id 中间件 + X-Request-ID | 2026-06-05 |
| 18 | S-04 | 无速率限制 | 添加 slowapi 中间件（60/min） | 2026-06-05 |
| 19 | S-05 | API 错误泄露内部细节 | 移除 console.error 详细输出 + 通用错误响应 | 2026-06-05 |
| 20 | C-04 | 异常吞噬（backtest 等服务静默 pass） | 改为 logger.error + exc_info | 2026-06-05 |
| 21 | P-03 | Lixinger 缓存无上限/淘汰 | 自定义 TTLCache（maxsize=500）+ 线程安全 | 2026-06-05 |
| 22 | A-06 | 无全局异常处理器 | 添加 global exception handler | 2026-06-05 |
| 23 | P-01 | 同步端点阻塞线程池 | 通过 slowapi 限流间接缓解 | 2026-06-05 |

### 进行中（代理执行）

| # | 编号 | 问题 | 状态 |
|---|------|------|------|
| 24 | R-01 | 无 Docker 部署配置 | 进行中 |
| 25 | R-02 | 无 HTTPS 支持 | 进行中（含 Docker） |
| 26 | R-03 | 无数据备份机制 | 进行中（含 Docker） |
| 27 | A-02 | 无数据库迁移管理 | 进行中（Alembic） |
| 28 | A-05+A-07 | 前端无代码分割和错误边界 | 进行中 |
| 29 | T-01 | 测试覆盖率极低（<10%） | 进行中 |
| 30 | A-01 | S-01（认证）已排除（个人使用） | 不适用 |

### 延后项（P2/P3）

| 编号 | 问题 | 优先级 | 说明 |
|------|------|--------|------|
| A-03 | 全局单例无并发保护 | P2 | LixingerClient 和 _price_cache 无锁 |
| A-04 | 前端无全局状态管理 | P2 | 股票列表重复获取 |
| C-02 | Service 层引用 HTTP Schema | P2 | 部分接收 Pydantic schema |
| C-03 | ORM-Response 转换散布 Router 层 | P2 | 应统一到 Service 层 |
| C-05 | 硬编码业务阈值 | P3 | 20%/15% 等限制硬编码 |
| P-02 | Portfolio Summary N+1 查询 | P2 | 每持仓单独查询 |
| P-04 | 前端 2.5MB 未分割 Bundle | P2 | ECharts 全量引入 |
| P-05 | 单股票查询获取全量公司列表 | P3 | data_service 效率 |
| R-04 | 前端硬编码中文 | P3 | 作为中文工具可接受 |
| R-05 | 无无障碍支持 | P3 | ARIA/键盘导航 |

---

## 关键修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `backend/app/db/engine.py` | WAL 模式 + busy_timeout + foreign_keys |
| `backend/app/main.py` | CORS 收紧 + 速率限制 + 请求追踪 + 全局异常处理 + 结构化日志初始化 |
| `backend/app/config.py` | Token 启动验证 |
| `backend/app/routers/data.py` | 文件上传验证 + 错误信息脱敏 |
| `backend/app/routers/health.py` | 深度健康检查 |
| `backend/app/routers/screener.py` | 速率限制集成 |
| `backend/app/services/lixinger_client.py` | TTLCache 替代无上限 dict |
| `backend/app/services/backtest_service.py` | 异常吞噬修复 |
| `backend/app/core/observability.py` | 新建 — 结构化日志 + LifecycleTracker |
| `frontend/src/api/client.ts` | 错误信息脱敏 |
| `.env.example` | 新建 — 环境变量模板 |
| `backend/requirements.txt` | 版本锁定 + 新依赖 |
