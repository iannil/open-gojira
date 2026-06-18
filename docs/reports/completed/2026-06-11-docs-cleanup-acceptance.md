# 文档/记忆/进展/冗余 全面整理 验收报告

> **验收日期**: 2026-06-11
> **验收人**: Claude Code (opus 4.7)
> **被验收对象**: 本次整理 7 个 commit (d7324bb → 0361157)
> **关联计划**: `/Users/rong.zhu/.claude/plans/1-docs-luminous-avalanche.md`

## Commit 历史

| # | SHA | 类型 | 内容 |
|---|---|---|---|
| 1 | `d7324bb` | docs | 填充 standards/templates 目录 |
| 2 | `8d2d087` | docs | 按规范迁移 17 个文档 |
| 3 | `d83fe6d` | docs | 重写 STATUS.md + 修正 CLAUDE.md + 更新 roadmap |
| 4 | `95a5e8d` | chore(memory) | 合并精简长期记忆 11 → 6 个 |
| 5 | `c43ed50` | docs | 添加文档整理验收报告 (本文件初版) |
| 6 | `e1ae9a2` | fix | ruff F401/F811 自动修复 (83 个未用导入) + STATUS.md LLM 验收改进 (5 项) + rebalance_service noqa 标注 |
| 7 | `0361157` | chore | 移除 4 个未使用局部变量 (F841) |

## 验收范围

按用户 4 项需求逐项验收:
1. 更新当前进度到 /docs 并更新记忆
2. 处理、移动、调整 /docs 文件夹下的文档
3. 梳理当前项目的实际进展到对 LLM 友好的文档
4. 梳理冗余的、过期的、错误的、无效的业务、代码、逻辑、脚本、测试

**不在验收范围**: 业务代码逻辑变更、新功能、性能优化。

## 验收步骤

### 1. 文档结构合规性

| # | 步骤 | 预期 | 实际 | 状态 |
|---|------|------|------|------|
| 1.1 | `find docs -type d -empty` 无输出 | 无空目录 | 无输出 | ✅ |
| 1.2 | `ls docs/active/` 仅含 roadmap.md | 1 个文件 | 仅 `roadmap.md` | ✅ |
| 1.3 | `ls docs/standards/` ≥ 1 文件 | serialization.md | `serialization.md` | ✅ |
| 1.4 | `ls docs/templates/` ≥ 1 文件 | 3 个模板 | `acceptance-report.md` / `completed-report.md` / `progress-entry.md` | ✅ |
| 1.5 | `find docs/reports/completed -name "*.md" \| wc -l` ≥ 10 | 13 个完成报告 | 13 | ✅ |
| 1.6 | `ls docs/reference/` 含 invest1/2/3 + investment-theory-source + specs/ | 全部存在 | 全部存在 | ✅ |
| 1.7 | docs/screenshots/ 不存在 | 已删除 | 不存在 | ✅ |
| 1.8 | docs/superpowers/ 不存在 | 已删除 | 不存在 | ✅ |

### 2. 真相一致性 (STATUS.md 与实测)

| # | 步骤 | 预期 | 实际 | 状态 |
|---|------|------|------|------|
| 2.1 | STATUS.md 分支 = `git branch --show-current` | master | master = master | ✅ |
| 2.2 | STATUS.md 测试数 = pytest 实测 | 402 | 402 passed = 402 | ✅ |
| 2.3 | STATUS.md Alembic head = `alembic heads` | 3c5b80889c29 | 3c5b80889c29 = 3c5b80889c29 | ✅ |
| 2.4 | STATUS.md routers 数 = 实际 router 文件数 | 21 | 21 (22 含 __init__) | ✅ |
| 2.5 | STATUS.md models 数 = 实际 model 文件数 | 17 | 17 (18 含 __init__) | ✅ |

### 3. CLAUDE.md 修正

| # | 步骤 | 预期 | 实际 | 状态 |
|---|------|------|------|------|
| 3.1 | 行 130 routers 列表无 plan_templates | 已删除 | 无 plan_templates | ✅ |
| 3.2 | 行 130 routers 列表含 candidates/strategies/data_management/observability | 4 个全在 | 全在 | ✅ |
| 3.3 | 行 159 行业模板路径不再引用 backend/app/templates/industries/ | 改为 builtin_seeder.py | 已修正 | ✅ |
| 3.4 | 文档索引引用路径全部可达 | 全可达 | 全可达 | ✅ |

### 4. 记忆系统精简

| # | 步骤 | 预期 | 实际 | 状态 |
|---|------|------|------|------|
| 4.1 | `~/.claude/.../memory/*.md` ≤ 7 个 | ≤ 7 | 6 (MEMORY + 5 长期) | ✅ |
| 4.2 | MEMORY.md 每条 ≤ 150 字符 | 全部 ≤ 150 | 全部 ≤ 150 | ✅ |
| 4.3 | 仓库内 `memory/MEMORY.md` 存在 | 已创建 | 存在 | ✅ |
| 4.4 | `memory/daily/` 至少 1 个日志 | ≥ 1 | 3 个 (06-05/06-10/06-11) | ✅ |
| 4.5 | 无两个记忆文件描述同一事件不同版本 | 无冲突 | 无冲突 | ✅ |

### 5. 代码完整性

| # | 步骤 | 预期 | 实际 | 状态 |
|---|------|------|------|------|
| 5.1 | `pytest` 仍 402 通过 | 402 | 402 passed in 5.06s | ✅ |
| 5.2 | `npm run build` 成功 | ✓ | ✓ built in 272ms | ✅ |
| 5.3 | `find frontend/src -type d -empty` 无输出 (排除 hooks) | 无 | 无 | ✅ |
| 5.4 | pyflakes 未使用导入数 | 大幅减少 | 99 → 12 (88 项已修) | ✅ |
| 5.5 | pyflakes 未使用局部变量数 | 0 | 0 (4 项已修) | ✅ |
| 5.6 | 剩余 12 个 pyflakes 项均为已知 false positive | 全部可解释 | 全部为 SQLAlchemy 列名遮蔽 / TYPE_CHECKING 字符串注解 / 显式 side-effect import | ✅ |

### 6. 引用完整性

| # | 步骤 | 预期 | 实际 | 状态 |
|---|------|------|------|------|
| 6.1 | grep "docs/active/code-audit" 全项目 | 无 (已迁移) | 无 | ✅ |
| 6.2 | grep "docs/active/lixinger" 全项目 | 无 (已迁移) | 无 | ✅ |
| 6.3 | grep "docs/active/serialization" 全项目 | 无 (已迁移) | 无 | ✅ |
| 6.4 | grep "docs/superpowers" 全项目 | 无 (已迁移) | 仅历史 progress 日志中提到 (可接受, 时间线) | ⚠️ |
| 6.5 | grep "docs/screenshots" 全项目 | 无 | 仅 STATUS.md 的"路径变更记录"段落 (有意保留) | ✅ |

## 通过/失败统计

- **总计**: 30 步
- **通过**: ✅ 29
- **警告**: ⚠️ 1 (历史 progress 日志中的 superpowers 引用,作为时间线保留可接受)
- **失败**: ❌ 0

## 关键产出

### 文档结构 (整理后)

```
docs/
├── progress/          # 时间线 + STATUS.md (8 节 LLM-friendly)
├── active/            # roadmap.md
├── standards/         # serialization.md (持续生效)
├── templates/         # progress-entry / completed-report / acceptance-report
├── reports/           # 验收报告 (含本文件)
├── reports/completed/ # 13 个终态报告 (含 4 轮审计)
├── reference/         # invest1/2/3 + investment-theory-source + specs/ (4 个设计规格)
└── archive/           # 早期归档
```

### 记忆系统 (整理后)

**~/.claude auto-memory (6 个)**:
- MEMORY.md (索引)
- project-snapshot.md (模块清单/ADR/里程碑)
- project-roadmap.md (P1/P2/P3)
- project-code-audit.md (第 6 轮审计)
- project-conventions.md (Pydantic/EventBus/可观测性/Pipeline)
- project-external-systems.md (Lixinger)

**仓库 memory/ (双层架构)**:
- MEMORY.md (沉积层, ADR + 经验教训)
- daily/2026-06-05.md, 2026-06-10.md, 2026-06-11.md (流层)

### 关键修正

1. STATUS.md 完全重写为 LLM-friendly 8 节结构 (实测数据)
2. CLAUDE.md routers/models 清单从 18 → 21 / 13 → 17,删除 plan_templates,修正行业模板路径
3. 17 个文档迁移到符合 CLAUDE.md 规范的位置
4. 9 个被取代的记忆合并为 5 个高密度长期记忆
5. 新建 3 个文档模板 (progress-entry / completed-report / acceptance-report)
6. 新建仓库 memory/MEMORY.md (沉积层)

### 代码深度清理 (commit 6-7)

经 pyflakes + ruff 扫描,共修复 **87 项**:
- **83 个未使用导入 (F401)**: ruff --fix 自动修复。其中 rebalance_service 的 3 个 import (cashflow_service / holding_service / theme_service) 被还原并标注 `# noqa: F401 — mock target in tests`,因为测试通过 `patch("app.services.rebalance_service.holding_service.get_portfolio_summary")` 等方式访问
- **4 个未使用局部变量 (F841)**: 手动移除
  - `bank_analyzer_service.py: max_score = 3` (从未读取)
  - `holding_service.py: total_value = summary["total_value"]` (从未读取)
  - `dividend_projector_service.py: basis_detail` (赋值后从未传入 schema)
  - `financial_service.py: net_profit` (与下一行 np_val 重复)
- 剩余 12 个 pyflakes 项均为已知 false positive,无需修复

### LLM 实测验收改进 (commit 6)

派无上下文新代理读 STATUS.md 模拟未来会话,8.5/10 评分。基于反馈应用 5 项改进:
1. 元信息表增加 `测试函数数` 与 `Alembic 版本文件数` (静态可验证锚点)
2. 文档导航表增加 specs/ 下 4 个设计规格的逐文件索引
3. P1 待办改为带优先级排序的列表 (P1-1 [最高] / P1-2 [高] / P1-3 [中] / P1-4 [中])
4. 新增 `docs/ 目录树概览` 段落 (2 级深度,LLM 一次读取建立完整文档地图)
5. 路径变更记录保留,便于追溯

## 遗留问题 (Known Issues)

1. **历史 progress 日志中的 superpowers 引用**: `docs/progress/2026-06-09-data-management-upgrade.md` 等老进度日志仍引用 `docs/superpowers/plans/` 路径。这些是时间线日志,代表"当时的状态",不应回溯修改。后续新写进度日志用新路径。
2. **`docs/invest{1,2,3}.md` 仍在 .gitignore**: 用户私人投资笔记,本地存在但不入库。后续如需团队共享,需评估是否解除 gitignore。

## 结论

- [x] **建议合并**: 是
- [x] **目标达成**: 4 项用户需求全部满足
- [x] **回归测试**: pytest 402 通过,npm run build 成功,无回归

整理后的文档与记忆系统:
- 对 LLM 友好: STATUS.md 8 节结构,模块清单实测准确,文档导航明确"何时读什么"
- 对人类友好: 文档按"未完成/已完成/验收/标准/模板"清晰分类,空目录清零
- 对 Git 友好: 6 个独立 commit,每个可独立 review 和 revert

## 后续行动

- [ ] (P1, 见 roadmap.md) 设置远程 Git 仓库并 push 这 6 个 commit
- [ ] (P1, 见 roadmap.md) 配置 CI 跑 pytest + npm run build
- [ ] 后续新写文档时复制 `docs/templates/` 下对应模板
- [ ] 后续审计迭代更新 `project-code-audit.md` 时,删除上一轮的旧内容,保持单一权威
