# 生产交付差距分析

> 时间：2026-06-26
> 与会者：用户 + reasonix
> 方式：/grill-me 深度访谈

## 背景

对 Gojira 个人股票自动驾驶舱进行全面生产交付差距分析，评估从当前状态（成熟度 2.1/5）到生产交付标准（3.0/5）需要补齐的缺口。

## 评估总览

| 维度 | 成熟度 | 关键发现 |
|:---|:---:|:---|
| 功能完整性 | **2.5 ↑** | Metrics 已可视化，Eval Set 基础设施就绪 |
| 代码质量 | **3.0 ↑** | scheduler v1 残留清理，边界澄清完成 |
| 测试覆盖率 | **2.5 ↑** | 14 条 E2E + 前端 vitest 框架，Eval Set 基线待接入 |
| 部署与运维 | **2.5 ↑** | DB 选型已统一，Runbook 已就绪，CI/CD 已搭建 |
| 文档与知识管理 | **3.0 ↑** | 部署 Runbook 已补齐，数据校验边界已澄清 |
| 安全与合规 | 2 | 维持单用户设计（无变化） |
| 监控与告警 | **2.5 ↑** | Phase 6 Tier 1 Metrics 运营度量 Dashboard 已上线 |
| 用户体验 | **3.0 ↑** | bundle 优化 + 组件测试框架 |
| **综合** | **2.65 ↑** | **从 2.1 提升至 2.65，距生产交付约 1-2 周** |

## 通过 Grill-Me 达成的 5 项关键决策

### 决策 1: DB 选型冲突 → 保留 SQLite，改 compose
- **问题**：docker-compose.yml 用 PostgreSQL，项目设计文档说"不做 PG 迁移"
- **选择**：保留 SQLite WAL，重写 docker-compose 移除 postgres 服务
- **工时**：0.5 天
- **理由**：不改 models/不改测试/不违背决策 25，改动最小

### 决策 2: scheduler v1 孤儿 job → 删注册，留框架
- **问题**：残留 8 个引用已删 v1 模块的 job，开启调度即 NameError
- **选择**：删除孤儿 job 注册行，保留空调度器框架
- **工时**：1 天

### 决策 3: CI/CD → GitHub Actions + Docker 镜像自动构建
- **问题**：无自动化流水线，每次部署手工操作
- **选择**：PR 自动 pytest + npm build + lint；main 合并自动 build Docker 镜像
- **工时**：1.5 天

### 决策 4: E2E 测试 → 先做 3-5 条核心路径
- **问题**：无端到端测试，无法自信回归
- **选择**：先做 E2E，Eval Set 排到 Phase 7
- **工时**：2 天

### 决策 5: Metrics + Runbook → 先灭 P0 火，后建设
- **问题**：Phase 6 Metrics 和部署 Runbook 都是 P1
- **选择**：先处理 P0 blockers（G1-G4），再回头补 Metrics + Runbook
- **工时**：后置

## 执行路线图

```
阶段 1 — P0 blockers（4 天） ✅
  ├─ G1: compose 改 SQLite volume 挂载         0.5 天  ✅
  ├─ G2: 清理 scheduler.py v1 孤儿 job           1 天  ✅
  ├─ G3: GitHub Actions + Docker 镜像构建        1.5 天  ✅
  └─ G4: E2E 测试 3-5 条核心链路                  2 天  ✅

阶段 2 — P1 基础设施（4 天） ✅
  ├─ G7: 部署 Runbook + 运维手册                  1 天  ✅
  ├─ G6: Phase 6 Tier 1 Metrics 可视化            3 天  ✅
  └─ 冷启动流程 + 估值/仓位触发接线                 2 天  🟡 用户选择手动

阶段 3 — P2+ 持续打磨（~5 天） ✅
  ├─ G5: Eval Set 20-30 家公司基线                 3 天  ✅ 基础设施就绪
  ├─ 两套 research API 合并                        1 天  ✅
  ├─ 前端 bundle 分块 + 组件测试                    3 天  ✅
  └─ 四个数据校验服务边界澄清                       0.5 天 ✅
```

## 差距项总表

| # | 差距项 | 优先级 | 工时 | 状态 |
|:---:|:---|---:|---:|:---:|
| G1 | docker-compose DB 选型冲突 | P0 | 0.5 天 | ✅ 已完成 |
| G2 | scheduler.py v1 孤儿 job | P0 | 1 天 | ✅ 已完成 |
| G3 | CI/CD 流水线 | P1 | 1.5 天 | ✅ 已完成 |
| G4 | E2E 测试（3-5 路径） | P1 | 2 天 | ✅ 已完成（14 条） |
| G5 | Eval Set 构建 | P1 | 3 天 | ✅ 基础设施就绪（Pipeline 回调待接入） |
| G6 | Metrics 可视化（Phase 6 Tier 1） | P1 | 3 天 | ✅ 已完成 |
| G7 | 部署 Runbook + 运维手册 | P2 | 1 天 | ✅ 已完成 |
| G8 | 估值止盈/仓位超限触发接线 | P2 | 2 天 | 🟡 用户选择手动处理 |
| G9 | 两套 research API 合并 | P3 | 1 天 | ✅ 已完成 |
| G10 | 前端 bundle 分块 | P3 | 1 天 | ✅ 已完成 |
| G11 | 前端组件测试 | P3 | 2 天 | ✅ 已完成（vitest + 4 测试） |
| G12 | 覆盖报告接入 | P3 | 0.5 天 | ⏳ 待处理 |
| G13 | 数据校验服务边界澄清 | P4 | 0.5 天 | ✅ 已完成 |
| G14 | 外部告警通道 | P4 | 1 天 | ⏳ 待处理 |
