# 不使用 Playwright E2E,改用 API smoke + 人工 UI checklist

2026-06-11 决定删除 `frontend/tests/e2e/` 全部 specs、`frontend/playwright.config.ts`、`@playwright/test` 依赖,以及 `backend/tests/test_lifecycle_e2e.py`(760 行 Playwright Python 驱动的 manual 生命周期脚本)。端到端回归改为「`backend/scripts/smoke_test.py`(Python httpx + Pydantic 校验,**不进 pytest**)+ 人工 UI checklist」混合模式。

理由:Gojira 是个人投资工具,业务 IA 在 2026-05 至 2026-06 经历多次重写(autopilot step1-4 删除 30+ 旧文件)。2026-06-06 写的 L1-L12 Playwright spec 在 IA 变化后立刻全部失效——引用了已删除的路由(`/screener`, `/analysis`, `/discipline`, `/compare`, `/portfolio?action=buy` 等)和已删除的 API(`/api/screener/run`, `/api/analysis`, `/api/discipline/checks` 等),跑 `npx playwright test` 必然全红。`backend/tests/test_lifecycle_e2e.py` 虽然引用当前路由(/universe, /stock/:code, /plans, /cockpit, /review)理论可跑,但它(1) 不被 pytest 发现(无 `def test_*`),(2) 是 manual screenshot 工具而非回归保护,(3) 与 `backend/scripts/smoke_test.py` 概念重叠且依赖更重(浏览器自动化)。Playwright 维护成本(每次 IA 变动需重写 12 步串行 spec)显著高于回归保护价值(单机部署、个人使用、后端单测 402 通过)。

## Considered Options

- **保留 Playwright + 重写 spec**:被拒。IA 还会动,单次重写需 4-6 小时,投入产出比差
- **归档 spec 但保留依赖**:被拒。死代码归档会误导后人以为 E2E 还活着
- **改用 Cypress / Testema**:被拒。同属 E2E 框架,问题等价

## Consequences

- 不再有"真实浏览器点击"的自动化回归。视觉 / 交互回归靠人工 checklist + 单元测试覆盖
- API 契约回归由 smoke 脚本承担(`backend/scripts/smoke_test.py`,独立调用,不与 402 单测混跑)
- 未来 CI(P1-3)只跑 `pytest` + `npm run build`,不跑 E2E
- 若未来项目转为多用户 / 团队工具,且 IA 稳定半年以上,可重新评估引入 Playwright

## 关联

- 决策来源:`docs/active/roadmap.md` P1-1(端到端手动验收)grill-with-docs 拷问过程
- 验收报告:`docs/reports/2026-06-11-e2e-round6-acceptance.md`(将创建)
