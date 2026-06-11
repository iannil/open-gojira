<!--
使用方法:
- 复制此模板到 docs/reports/completed/
- 命名格式: {type}-{topic}-{YYYY-MM-DD}.md (例如 plan-foo-bar-2026-06-15.md)
- 此类文档记录"已完成"的修改,是终态报告;不可继续编辑,有问题在新 progress-entry 中记录
- type 推荐: plan / audit / refactor / migration / feature
-->

# {标题}

> **完成日期**: {YYYY-MM-DD}
> **开始日期**: {YYYY-MM-DD}
> **作者/执行人**: {人或 AI 代理}
> **关联进度日志**: `docs/progress/{xxx}.md`

## 目标 (Goal)

{本次工作要解决的问题。从用户/业务视角描述,而非技术实现。}

## 最终状态 (Final State)

{1-3 段话描述交付的成果。让读者无需阅读细节就能理解最终交付了什么。}

## 关键修改 (Key Changes)

{按"修改类型"或"模块"分组列出。每条标注文件路径。}

### 后端
- `path/to/file.py`: 一句话说明

### 前端
- `path/to/file.tsx`: 一句话说明

### 数据库
- Alembic migration `{revision_id}`: 一句话说明

### 文档
- `path/to/doc.md`: 一句话说明

## 测试结果 (Test Results)

```
pytest: XXX passed, 0 failed
npm run build: ✓
npm run lint: 0 errors
```

{如有失败或跳过的测试,在此说明原因。}

## 验收检查 (Acceptance Checklist)

- [ ] 功能验收: {手工或自动化测试通过}
- [ ] 回归测试: {既有功能未受影响}
- [ ] 文档更新: {相关文档已同步}
- [ ] 性能验收: {关键路径性能未退化}

## 遗留问题 (Known Issues, 可空)

{本次未解决的问题,后续在 roadmap.md 或新 progress-entry 中跟踪。}

- {问题描述} → 跟踪于 {roadmap P? / 新 progress log}

## 参考 (References, 可空)

- 设计文档: `docs/reference/specs/{xxx}.md`
- 上游审计: `docs/reports/completed/{audit}.md`
- ADR / 关键决策: {位置}
