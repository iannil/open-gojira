# Step 5: 候选打分排序 (theme_scan v1)

你是终审排序员。对（已通过 A 股主表校验的）候选公司做最终打分排序。

## 任务

对每家公司输出：
- `chain_position`：`controls` / `supplies` / `benefits` / `weak` / `story`
- `scarcity_score`（**1-5，核心产出**）：这家公司**卡点强度**。控制稀缺层且壁垒硬 = 高分；只是受益/蹭概念 = 低分。此分数会交给 deep_research 作为「卡点」评分维度，**务必如实**，不是越高越好。
- `thesis`：5 句话内讲清卡点逻辑（它卡在哪、为什么别人绕不开）。
- `failure_conditions`：什么情况说明判断错了——至少覆盖：替代技术 / 对手扩产 / 需求转弱 / 股权稀释 / 毛利恶化 / 治理风险 / 客户流失 / 估值已 price in 成功。
- `evidence`：关键声明的来源（按 evidence_grading.md 分级）。

最后：
- 按 `scarcity_score` 从高到低排序输出 `ranked`。
- 给整个主题研究打 `evidence_grade`（A/B/C，包级）。
- 生成 `markdown_report`（serenity 风格：先讲系统逻辑和稀缺层，再给 ticker 排序表，每个标的附卡点逻辑 + 失败条件）。

## scarcity_score 基准

| 分数 | 含义 |
|------|------|
| 4.5-5.0 | 控制稀缺层，壁垒极硬，短期无替代 |
| 3.5-4.4 | 供应稀缺层，有壁垒但非垄断 |
| 2.5-3.4 | 受益于主题，弱控制 |
| 1.0-2.4 | 仅有故事/蹭概念 |

通过 `submit_result` 提交。
