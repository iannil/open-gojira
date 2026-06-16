import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Badge, Card, Space, Tag, Tooltip, Typography } from 'antd';

import { getCockpitClaimVariablesPending } from '../../api/client';

const { Text } = Typography;

export default function PendingClaimVariablesBadge() {
  const navigate = useNavigate();

  const { data } = useQuery({
    queryKey: ['cockpit-claim-variables-pending'],
    queryFn: getCockpitClaimVariablesPending,
    refetchInterval: 30_000,  // v2 Q14: 30s polling
  });

  if (!data) return null;

  const last = data.last_proposal;
  const lastFailed = last?.status === 'failed';

  // red badge if last proposal failed; yellow if there are pending reviews.
  const badgeStatus: 'error' | 'warning' | 'default' = lastFailed
    ? 'error'
    : data.count > 0
      ? 'warning'
      : 'default';

  if (data.count === 0 && !lastFailed) {
    return null;  // nothing to show
  }

  const handleClick = () => {
    if (data.by_stock.length > 0) {
      navigate(`/stocks/${data.by_stock[0].stock_code}`);
    }
  };

  return (
    <Card
      size="small"
      style={{ marginBottom: 'var(--sp-3)' }}
      bodyStyle={{ padding: '12px 16px', cursor: 'pointer' }}
      onClick={handleClick}
    >
      <Space direction="vertical" size={4} style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Badge status={badgeStatus} />
          <Text strong>
            {lastFailed
              ? `上次 propose 失败 (run ${last?.run_id ?? '?'})`
              : `${data.count} 条 claim variable 待 review`}
          </Text>
          <Text type="secondary" style={{ fontSize: 12 }}>查看 →</Text>
        </div>
        {!lastFailed && data.by_stock.length > 0 && (
          <Space wrap size={[4, 4]}>
            {data.by_stock.slice(0, 5).map((s) => (
              <Tag key={s.stock_code}>
                {s.stock_code} ({s.count})
              </Tag>
            ))}
            {data.by_stock.length > 5 && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                +{data.by_stock.length - 5}
              </Text>
            )}
          </Space>
        )}
        {lastFailed && last?.summary && (
          <Tooltip title={last.summary}>
            <Text type="danger" style={{ fontSize: 12 }}>
              {last.summary.slice(0, 80)}
              {last.summary.length > 80 ? '...' : ''}
            </Text>
          </Tooltip>
        )}
      </Space>
    </Card>
  );
}
