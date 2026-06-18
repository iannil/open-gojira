# Serenity Skill 集成实施 (2026-06-15)

> 状态: Phase 1 后端 + 前端主体完成,等 GLM 余额充值后跑真实研究验收
> 关联规格: `docs/reference/specs/2026-06-14-serenity-skill-integration.md` (19 项决策完整记录)

## 背景

基于 grill-me 会话产出的 19 项决策(Q1-Q9 核心架构 + Q10-Q19 实施细节),在 Gojira
内嵌实现 serenity-skill 研究工作流。

serenity-skill 核心:`市场叙事 → 系统变化 → 价值链 → 稀缺层 → 上市公司 → 证据分级
→ 排名 → 失败条件 → 下一步验证`。

## 实施记录

### Phase 0: Spike (Day 1-2) — 部分完成

- ✓ zhipuai SDK 安装 (v2.1.5.20250825)
- ✓ SYSTEM_PROMPT + SERENITY_RESEARCH_JSON_SCHEMA 设计
- ✓ Lixinger 字段映射修正 (stockCode / stockName.cmn_hans_cn)
- ✓ Pydantic Settings 扩展 (ZHIPU_* / SERENITY_* + extra=ignore)
- ✗ **GLM API 调用阻塞** — 账号 429 余额不足 (code 1113)
  - GLM-5.2 / GLM-4.7 都触发,说明是账号问题
  - 用户决定暂停 spike,先推 Day 3+ 后端实现
  - spike 等 GLM 账号充值后再跑真实验证

**Commit**: `7414918 feat(serenity): spike 阶段基础设施 (Day 1-2)`

### Phase 1: Day 3-4 后端骨架

**Day 3 后端骨架**:

- ✓ 7 ORM models (`research_theme` / `research_run` / `value_chain_layer` /
  `scarce_layer` / `research_company_universe` / `research_evidence` /
  `research_company_ranking`) 含 Q14 三处 stock_code index
- ✓ Alembic migration `s1_serenity_research_module` (head 推进)
- ✓ 7 Pydantic schemas
- ✓ `ZhipuClient` (复用 spike 验证过的 prompt + JSON schema,无 LLMProvider
  抽象 — Q16)
- ✓ `ResearchRunnerService` (Q10 异步 ThreadPoolExecutor / Q13 三重硬约束 /
  Q8 retry + 月度预算软上限 / Q17 EventBus 告警)
- ✓ `ResearchPersistenceService` (LLM 输出 → 6 子表 + 校验 ≥20 公司 /
  ≥25 证据 / 3-7 排名)
- ✓ `ResearchContextBuilder` (Lixinger 行业成分股装配,fallback LLM-only)
- ✓ `ResearchExportService` (Q11 Phase 1 仅 watchlist,Candidate 留 Phase 2)
- ✓ EventBus 3 个新事件: `ResearchRunCompleted` / `ResearchRunFailed` /
  `MonthlyBudgetExceeded`

**Day 4 router + scheduler**:

- ✓ `/api/research/*` 10 endpoints (CRUD + run + export + appearances)
- ✓ `weekly_research_refresh` cron (周一 8am Asia/Shanghai)
- ✓ Q12 scheduler 跳过 `last_run_status='failed'`
- ✓ EventBus 订阅 `ResearchRunFailed` / `MonthlyBudgetExceeded` → SystemAlert
  → 复用 NotificationChannel (Q17)
- ✓ 修正现有 `test_scheduler.py` 加 weekly_research_refresh 到 JOB_REGISTRY

**Commit**: `6e5a0b4 feat(serenity): Day 3-4 后端骨架完整`

### Phase 1: Day 5 前端 UI

- ✓ 装依赖: `react-markdown` + `remark-gfm` + `rehype-raw` (Q18)
- ✓ 路由: `/research` + `/research/:themeId` 注册
- ✓ 导航: Layout 加 "研究 / Research" 菜单项(策略组首位,体现 serenity 是策略上游)
- ✓ API 层: `types.ts` 加 13 个 TypeScript 类型 / `client.ts` 加 9 个 API 函数
- ✓ `ResearchThemesPage` (列表 + 新建 modal + 归档)
- ✓ `ResearchThemeDetailPage` 6 tab:
  - Overview: 系统变化 + 稀缺层排名 + Top 3-7 公司卡片 + token 统计 + 导出按钮
  - Value Chain: 8 层表格
  - Companies: 公司宇宙 ≥20 表格(分类徽章 controls/supplies/benefits/weak/story)
  - Evidence: 证据链按 grade 排序 (strong→medium→weak→lead)
  - Failure: 失败条件 + 下一步验证 (Markdown 渲染)
  - History: 历史 Run 列表
- ✓ 导出 modal: 选 watchlist 分组 + rank_max → POST `/runs/{id}/export`
  (Q11 不弹 DisciplineChecklistModal)

**辅助入口(Q7 D 决策的 4 个入口中已完成 2 个,剩 3 个)**:
- ✓ 主页面 `/research`
- ✓ StockDetail 反向链接(通过 `appearances/{code}` API + 端点 ready,
  Phase 2 加 UI panel)
- ✗ Cockpit "今日 serenity" 卡片 (Phase 2)
- ✗ Candidates source 徽章 (Phase 2,需 Candidate 表加 source 字段)

**Commit**: `33a5734 feat(serenity): Day 5 前端 UI 主体`

### Phase 1: Day 6 后端测试

5 个测试文件 / 34 个新测试 / 总 972 测试通过(938 → 972,0 回归):

- `test_research_persistence_service.py` (7 个): 6-table 持久化 / schema 校验 / FK
- `test_research_runner_service.py` (5 个): Q10 异步 / Q6 限频 / 状态校验
- `test_research_export_service.py` (5 个): Q3 D 导出 / Q11 跳过重复 / Phase 1 candidate
- `test_research_scheduler_service.py` (6 个): Q6 cron / Q12 跳过 failed
- `test_research_router.py` (11 个): 完整 CRUD + 触发 + 导出 + 反向链接

**Commit**: `4f08700 test(serenity): Day 6 后端测试 ≥15 个`

## 当前状态

| 维度 | 状态 |
|---|---|
| Phase 1 后端 | ✓ 完整 (models + services + router + scheduler + tests) |
| Phase 1 前端 | ✓ 主体完整 (列表 + 详情 + 6 tab + 导出) |
| Phase 1 测试 | ✓ 34 个新测试 / 972 总通过 |
| Phase 1 文档 | ✓ 本文档 + spec (2026-06-14) |
| Phase 0 Spike | ⏸ 阻塞 (GLM 账号 429 余额不足) |
| 端到端真实验证 | ⏸ 等 GLM 充值后跑 2 次真实研究 |
| 辅助入口 (Q7 D) | ⏸ Cockpit 卡片 / Candidates 徽章 / StockDetail panel (Phase 2) |
| 失败条件 → 论点变量 | ⏸ Q19 Phase 2 |

## 阻塞与下一步

### P0 (阻塞真实使用)

1. **解 GLM 账号余额**:访问 https://open.bigmodel.cn/usercenter/overview 查余额 + 充值
   (¥10-20 足够 5-10 次完整研究)
2. **跑首次 spike**: GLM 充值后,执行
   ```
   cd backend && source .venv/bin/activate
   python spikes/serenity_glm_spike.py
   ```
   按 spec Day 1 下午 8 维评估表打分
3. **跑真实研究**: UI 触发或 `curl POST /api/research/themes/{id}/run`,验证:
   - 公司宇宙 ≥20 / 证据 ≥25 / 排名 3-7
   - GLM-5.2 是否可用 (Coding Plan 付费)
   - LLM 实际 token 消耗 vs 预算上限

### P1 (验收 Phase 1)

4. **更新 STATUS.md**: 加入 serenity 模块 / 7 表 / 10 endpoint / 972 测试
5. **写完成报告**: `docs/reports/completed/serenity-skill-integration-2026-06-15.md`

### P2 (后续)

6. Cockpit "今日 serenity" 卡片
7. Candidates source 徽章(需 Candidate 表加 source 字段 + migration)
8. StockDetail 反向链接 panel(端点已 ready,加 UI 即可)
9. 失败条件 → 论点变量转译(Q19)
10. 历史 Run diff 视图(Q15)

## 关键文件索引

后端:
- `backend/app/models/research_*.py` (7 个 ORM)
- `backend/app/schemas/research.py` (13 个 Pydantic)
- `backend/app/services/research_*.py` (4 个 service)
- `backend/app/services/llm/` (ZhipuClient + prompts)
- `backend/app/routers/research.py` (10 endpoints)
- `backend/app/core/research_config.py`
- `backend/alembic/versions/s1_serenity_research_module.py`
- `backend/tests/test_research_*.py` (5 个测试文件)
- `backend/spikes/serenity_glm_spike.py`

前端:
- `frontend/src/features/research/ResearchThemesPage.tsx`
- `frontend/src/features/research/ResearchThemeDetailPage.tsx`
- `frontend/src/pages/Research{Themes,ThemeDetail}Page.tsx` (重导出)
- `frontend/src/api/{types,client}.ts` (research 相关)
- `frontend/src/components/Layout.tsx` (菜单项)
- `frontend/src/App.tsx` (路由)

文档:
- `docs/reference/serenity-skill/` (方法论副本,MIT)
- `docs/reference/specs/2026-06-14-serenity-skill-integration.md` (19 决策规格)
- `docs/progress/2026-06-15-serenity-skill-integration.md` (本文档)
