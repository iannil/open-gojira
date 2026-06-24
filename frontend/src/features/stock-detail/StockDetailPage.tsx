import { useParams } from 'react-router-dom';
import { Result } from 'antd';

/**
 * StockDetail — v2 stub.
 *
 * v1 StockDetailPage 已移除（依赖 QiuScorerWizard + thesis variables + business pattern）。
 * Phase 3 将重建，整合 v2 研究报告展示。
 */
export default function StockDetailPage() {
  const { code } = useParams<{ code: string }>();
  return (
    <Result
      status="info"
      title={`Stock Detail — ${code || '?'} — v2 待重建`}
      subTitle="v1 StockDetailPage 已移除。Phase 3 将重建，整合 v2 研究报告展示。"
    />
  );
}
