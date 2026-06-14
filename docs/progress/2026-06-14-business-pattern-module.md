# 商业模式模块 (BusinessPattern / 产业研究)

> **日期**: 2026-06-14
> **状态**: 已完成 (v1)
> **关联**: invest1/2/3.md 方法论; thesis_variable_sync_service 重构

## 目标 (Goal)

把 invest1/2/3 文档里散落的"产业研究"方法论(顶层设计找势 / 第一性原理找核心变量 / "求"字理论找话语权 / 分类筛选框架)沉淀为 Gojira 的**第一公民数据对象**:BusinessPattern(生意模式)。

让"产业研究"从**散落在 Stock 字段里**升级为**独立可管理的 context 层**,在不引入"AI 做决策"的前提下(符合 invest docs 的"独立思考"原则),让用户:
- 在 UI 上看到每只股票归属的生意模式 + 核心变量(可解释性)
- 在 Review 时被提示"该关注 X"(审计指引)
- 自动从 Lixinger industry 推断关联(流程自动化,保护用户 override)

## 范围 (Scope)

**v1 覆盖**(决策编号见下文"12 项设计决策"):
- BusinessPattern 表 + Alembic migration
- 17 个 builtin patterns seed(覆盖 invest docs 显式案例 + 必要扩展)
- business_pattern_service(CRUD + infer_business_pattern 纯函数 + 用户 override 保护)
- thesis_variable_sync_service 改造:数据源从硬编码常量 → DB(BusinessPattern.thesis_variables_json)
- stocks router 暴露 business_pattern 字段 + PATCH endpoint(手动 override)
- business_patterns router(完整 CRUD + /infer-all + /thesis-templates)
- Stock 同步时自动推断 hook(Stock 入库 + industry 变更触发)
- 前端:新菜单"商业模式" + 独立页面 + StockDetail "商业模式" panel + Review "核心变量提示"列

**不在 v1 范围内**(已决定延后):
- (B) strategy_engine 注入 effective_power_tier(策略规则可选引用)
- (C) Plan DSL 加 business_pattern_in 过滤条件
- (δ) Candidates 加 "商业模式" 列
- 自动推断的定期 batch job(用户用 /infer-all 手动触发)

## 12 项设计决策(grill-me 2026-06-14)

| # | 决策点 | 选择 |
|---|---|---|
| 1 | 模块定位 | (C) 设计 Gojira 产业研究能力 |
| 2 | 产出语义 | Context 型(非 Decision) |
| 3 | 粒度 | (b) 生意模式 BusinessPattern |
| 4 | 与 sync_service 关系 | (c) 桥接,常量降级为 seeder |
| 5 | 字段集 | (b) 中等覆盖,7+ 字段 |
| 6 | 维护模式 | (c) Seeder bootstrap + UI 编辑 + is_builtin |
| 7 | 关联策略 | (c) 自动推断 + UI override;歧义留 null 强制手标 |
| 8 | v1 下游消费 | (A) UI/Review 展示 + (D) Review 核心变量提示 |
| 9 | 初始 seed 范围 | (b) docs + 必要扩展,~17 patterns |
| 10 | UI 注入点 | (α) 独立路由 + (β) StockDetail panel + (γ) Review 列 |
| 11 | 自动推断触发时机 | (i) 入库 + (ii) industry 变更 + (iv) 手动 trigger |
| 12 | 清理字段决策 | A1 (source_ref) + B2 (inferred_at) + C4 (菜单名"商业模式") |

## 变更摘要 (Changes)

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/app/models/business_pattern.py` | 新增 | BusinessPattern ORM 模型,8 字段 |
| `backend/app/models/__init__.py` | 修改 | 注册 BusinessPattern |
| `backend/app/models/stock.py` | 修改 | 加 business_pattern_id + business_pattern_inferred_at |
| `backend/alembic/versions/t6_1_business_patterns.py` | 新增 | Migration:business_patterns 表 + Stock FK 字段 |
| `backend/app/schemas/business_pattern.py` | 新增 | Pydantic schemas |
| `backend/app/schemas/stock.py` | 修改 | StockResponse 加 business_pattern_* 字段 |
| `backend/app/services/business_pattern_service.py` | 新增 | CRUD + infer_business_pattern 纯函数 + override 保护 |
| `backend/app/services/builtin_seeder.py` | 修改 | 加 BUILTIN_BUSINESS_PATTERNS (17 个) + seed_business_patterns() |
| `backend/app/services/thesis_variable_sync_service.py` | 重构 | 数据源从常量 → BusinessPattern DB |
| `backend/app/services/data_service.py` | 修改 | stock_to_response 加 business_pattern_* |
| `backend/app/services/review_service.py` | 修改 | by_stock 补 business_pattern_name + first_principle_variable |
| `backend/app/services/stocks_sync_service.py` | 修改 | industry 同步后调用 infer_all_stocks |
| `backend/app/services/pipelines/universe_bootstrap_pipeline.py` | 修改 | bootstrap 后调用 infer_all_stocks |
| `backend/app/routers/business_patterns.py` | 新增 | /api/business-patterns CRUD + infer-all + thesis-templates |
| `backend/app/routers/stocks.py` | 修改 | PATCH /stocks/{code}/business-pattern 端点;get_thesis_templates 改读 pattern |
| `backend/app/main.py` | 修改 | 注册 business_patterns router |
| `backend/tests/test_business_pattern_service.py` | 新增 | 纯函数 + CRUD + 推断 + override 保护(19 tests) |
| `backend/tests/test_business_patterns_router.py` | 新增 | API 端点(10 tests) |
| `backend/tests/test_thesis_variable_sync.py` | 重写 | 适配新数据源(10 tests) |
| `frontend/src/api/types.ts` | 修改 | BusinessPattern / ThesisVariableTemplate / InferAllSummary;StockResponse + ReviewByStock 扩字段 |
| `frontend/src/api/client.ts` | 修改 | 加 listBusinessPatterns / create / update / delete / inferAll / getThesisTemplates / updateStockBusinessPattern |
| `frontend/src/features/business-patterns/` | 新增 | queries.ts / useBusinessPatternQueries.ts / useBusinessPatternMutations.ts / BusinessPatternsPage.tsx |
| `frontend/src/pages/BusinessPatternsPage.tsx` | 新增 | 页面 wrapper |
| `frontend/src/App.tsx` | 修改 | lazy import + Route /business-patterns |
| `frontend/src/components/Layout.tsx` | 修改 | 菜单"商业模式" + ClusterOutlined icon |
| `frontend/src/features/stock-detail/components/IndustryContextPanel.tsx` | 新增 | 商业模式 context panel + 手动 override |
| `frontend/src/features/stock-detail/StockDetailPage.tsx` | 修改 | 嵌入 IndustryContextPanel(基本信息之后) |
| `frontend/src/features/review/ReviewPage.tsx` | 修改 | StockTable 加 "商业模式" + "核心变量" 列 |
| `frontend/src/features/stock-detail/components/ThesisVariablesModal.tsx` | 修改 | 无模板时的提示引导用户去关联商业模式 |

## 验证 (Verification)

- [x] 后端测试: 852 通过(原 823 + 29 新增)
- [x] 前端 build: 成功
- [x] 前端 lint: 我修改的所有文件零 issue(预存的 1 error 8 warning 与本次无关)
- [x] Alembic migration: 注册为 head (`t6_1_business_patterns`)
- [x] 路由注册: `/api/business-patterns` + 7 个端点
- [x] 自动推断路径: stocks_sync_service / universe_bootstrap_pipeline 都已 hook
- [ ] 端到端: 需要启动后端实际 seed 17 个 pattern + 跑一次 infer-all,确认 stocks 表大量 business_pattern_id 被填充(留待用户验收)

## 17 个 builtin patterns

| 生意模式 | 主题 | 第一性原理核心变量 | "求"字位阶 | Lixinger industries | source_ref |
|---|---|---|---|---|---|
| 煤化工 | 能源安全 | 煤油价差套利 | 2 | 化学原料/化学制品/煤化工 | invest1 第二章; invest2 BFNY; invest3 §12 |
| 纯煤开采 | 能源安全 | 煤价 × 可采储量 × 品位 | 2 | 煤炭开采/煤炭 | invest3 §12 |
| 电解铝 | 资源安全 | 电力成本套利(出海) | 1 | 工业金属/有色冶炼 | invest1 第二章; invest2 NSLY |
| 铝上游 | 资源安全 | 铝土矿自给率与氧化铝价差 | 2 | 工业金属/有色冶炼 | invest3 §12 |
| 磷化工 | 资源安全 | 磷矿品位/储量 | 2 | 化学原料/化学制品 | invest2 BTGF/CHGF; invest3 §12 |
| 钾肥 | 资源安全 | 钾肥价格 × 矿石品位 | 2 | 化学原料/化学制品 | invest3 §12 |
| 铜矿 | 资源安全 | 铜价 × 储量 | 2 | 工业金属/有色金属 | invest3 §12 |
| 锡矿 | 资源安全 | 锡价 × 储量 | 2 | 有色金属 | invest3 §12 |
| 黄金矿企 | 金融安全 | 储量 × 金价 - 单位采金成本 | 2 | 黄金/有色金属 | invest3 §12 |
| 黄金零售 | 金融安全 | 金价 × 成交量 | 1 | 珠宝首饰/零售 | invest2 菜百 |
| 银行 | 金融安全 | 股息 + 地域 + 长周期现金流/净利润匹配 | 1 | 银行 | invest3 §11 盲盒可视化 |
| 保险 | 金融安全 | 内含价值与新业务价值 | 1 | 保险/保险Ⅱ | invest3 §23 资产配置 |
| 证券 | 金融安全 | 日均股基交易量 | 1 | 证券/证券Ⅱ | invest3 §23 资产配置 |
| 电力 | 能源安全 | 利用小时数 × 上网电价 | 2 | 电力/电力Ⅱ | invest3 §13 公用事业 |
| 植物生长剂 | 粮食安全 | 农资涨价下的增效需求 | 1 | 农药/农化制品 | invest2 GGGF |
| 药店零售 | (null) | 加盟店增速 | 2 | 医药商业/医药流通 | invest2 DSL |
| 旅游景区 | (null) | 客流 × 索道票均价 | 2 | 旅游零售/酒店餐饮/景点 | invest2 九华旅游 |

**注意**:
- "药店零售" / "旅游景区" 的 theme_id 为 null(民生主线未在 themes 表中,留 v2 决定是否扩 Theme 表)
- "煤炭开采" / "铝" / "黄金" 这三个 Lixinger industry 字符串在多个 pattern 中出现,**会触发 1:多 歧义**,**自动推断留 null**,用户在 StockDetail 手动关联
- 银行 4 个 thesis_variables 是 `source: lixinger`(可自动 sync),其他全部 manual

## 数据迁移注意

**部署后第一次启动会自动**:
1. 创建 business_patterns 表 + Stock 新字段
2. Seed 17 个 builtin patterns
3. **首次启动不会自动跑 infer_all_stocks**(只在 industry 同步触发时跑)

**用户首次访问 /business-patterns 页面时,可以点"重新推断"按钮**:
- 第一次会扫描所有 stocks,按 industry 字符串匹配
- 跳过用户已 override 的(inferred_at IS NULL + id NOT NULL)
- 返回 `{total, updated, protected, cleared}` 摘要

## 下一步 (Next Steps)

**v2 候选**(按问题 8 决策延后项):
1. **strategy_engine 注入 effective_power_tier** — StockContext 加 derived field,策略规则可选引用 `pattern.power_tier_baseline`
2. **Plan DSL 加 business_pattern_in 过滤** — 让 Plan 可按产业圈定扫描范围
3. **Candidates 加 "商业模式" 列** — 候选池展示产业分布
4. **定期 batch 推断** — 周度 cron job 兜底(若用户反馈手动 trigger 不够及时)

**Theme 表扩展候选**:
- 加 "民生" / "科技" / "信息" 三条主线条目(目前只有 4 个:能源/资源/金融/粮食)
- 让药店零售 / 旅游景区 / AI / 网络安全等 pattern 有 theme 归属

## 参考 (References)

- 设计对话: grill-me 12 轮(2026-06-14)
- 文档方法论:
  - invest1 第二章:第一性原理 + "求"字理论
  - invest2:6 个具体公司案例 + thesis variables
  - invest3 第十二节:资源股七步顺序 + 行业偏好
  - invest3 第二十六节:选股流程七步(本次实现了 step 1-3 的"行业层"沉淀)
- 演进路径:与 `builtin_seeder.py` 同款(seeder bootstrap + UI 编辑 + is_builtin 区分)
