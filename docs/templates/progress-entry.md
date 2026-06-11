<!--
使用方法:
- 复制此模板到 docs/progress/
- 命名格式: {YYYY-MM-DD}-{topic}.md (例如 2026-06-15-add-foo.md)
- 此类文档记录"未完成或进行中"的修改;一旦完成,移到 docs/reports/completed/
- AI 代理应优先阅读 docs/progress/STATUS.md,然后按时间倒序阅读最新进度日志
-->

# {标题}

> **日期**: {YYYY-MM-DD}
> **状态**: 进行中 | 已完成 | 已阻塞
> **关联**: {相关 issue / PR / 上游决策的文档路径,可空}

## 目标 (Goal)

{1-2 句话描述本次修改要解决的问题或达成的目标。说明 why,不只是 what。}

## 范围 (Scope)

- **影响模块**: {后端 service / router / 前端 page / migration / ...}
- **不在范围内**: {明确排除的内容,避免 scope creep}

## 变更摘要 (Changes)

{用列表或表格列出关键修改,每条附文件路径。}

| 文件 | 修改类型 | 说明 |
|---|---|---|
| `path/to/file.py` | 新增 / 修改 / 删除 | 一句话说明 |

## 验证 (Verification)

{如何确认本次修改正确?}

- [ ] 单元测试: `pytest tests/test_xxx.py`
- [ ] 端到端测试: {手动或自动}
- [ ] 类型检查: `npm run build` / `mypy`
- [ ] 回归测试: {哪些既有功能需要确认未受影响}

## 下一步 (Next Steps)

{若未完成,列出剩余工作;若已完成,本节留空或改为"完成日期 + 后续待办"。}

## 参考 (References, 可空)

- {设计文档 / ADR / 外部链接}
