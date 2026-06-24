import { Result, Button } from 'antd';

/**
 * Cockpit — v2 stub.
 *
 * v1 cockpit 已移除（依赖已删的 strategy/plan/research 模块）。
 * Phase 3 将重建为信号优先 dashboard：
 *   - 顶部：待办信号（Drafts 待审批）
 *   - 中部：持仓概览
 *   - 底部：候选池 + 观察池
 */
export default function CockpitPage() {
  return (
    <Result
      status="info"
      title="Gojira v2 — Cockpit 待重建"
      subTitle="v1 cockpit 已移除。Phase 3 将重建为信号优先 dashboard。"
      extra={<Button type="primary" href="/drafts">查看 Drafts</Button>}
    />
  );
}
