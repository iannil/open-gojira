import { useMemo } from 'react';
import { Button, Card, Col, Row, Space, Statistic, Tag, Typography, Progress } from 'antd';
import {
  CheckCircleOutlined,
  CloudSyncOutlined,
  ReloadOutlined,
  WarningOutlined,
} from '@ant-design/icons';

import {
  useApiUsageQuery,
  useDataStatusQuery,
  useDeadLetterStatsQuery,
  usePipelineHealthQuery,
} from '../useDataQueries';
import {
  DATA_TYPES,
  DATA_TYPE_ICONS,
  DATA_TYPE_LABELS,
  FRESHNESS_COLORS,
  FRESHNESS_LABELS,
} from '../constants';

const { Text } = Typography;

interface Props {
  onSync: () => void;
}

function FreshnessDot({ freshness }: { freshness: string }) {
  const color = FRESHNESS_COLORS[freshness] || '#d9d9d9';
  return (
    <span
      style={{
        display: 'inline-block',
        width: 8,
        height: 8,
        borderRadius: '50%',
        backgroundColor: color,
        marginRight: 6,
      }}
    />
  );
}

export default function DataHealthDashboard({ onSync }: Props) {
  const statusQ = useDataStatusQuery();
  const healthQ = usePipelineHealthQuery();
  const apiUsageQ = useApiUsageQuery();
  const deadLetterQ = useDeadLetterStatsQuery();

  const status = statusQ.data;
  const health = healthQ.data;
  const apiUsage = apiUsageQ.data;
  const deadLetterStats = deadLetterQ.data;

  const overallScore = useMemo(() => {
    if (!health || !status) return 0;
    let total = 0;
    for (const dtype of DATA_TYPES) {
      const h = health[dtype];
      const s = status[dtype];
      if (!h) continue;
      const freshScore = h.fresh ? 40 : 20;
      const coverageScore =
        s && s.stock_count > 0
          ? Math.min((s.stock_count / Math.max(s.total_records, 1)) * 30, 30)
          : 0;
      const volumeScore = s && s.total_records > 0 ? 30 : 0;
      total += freshScore + coverageScore + volumeScore;
    }
    return Math.round(total / DATA_TYPES.length);
  }, [health, status]);

  const scoreColor =
    overallScore >= 80 ? 'var(--green-600)' : overallScore >= 50 ? 'var(--amber-600)' : 'var(--red-600)';

  // Combined refresh: invalidate all 4 queries. They share ['data-management'] namespace.
  const RefreshBtn = (
    <Button
      icon={<ReloadOutlined />}
      onClick={() => {
        statusQ.refetch();
        healthQ.refetch();
        apiUsageQ.refetch();
        deadLetterQ.refetch();
      }}
    >
      刷新状态
    </Button>
  );

  // Any of the 4 still loading on first mount → big spinner.
  const anyLoading =
    (statusQ.isLoading || healthQ.isLoading || apiUsageQ.isLoading || deadLetterQ.isLoading) &&
    !status;

  if (anyLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 60 }}>
        <Progress type="circle" percent={50} status="active" />
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
      <Row gutter={16}>
        <Col span={8}>
          <Card className="gojira-card" bordered={false} title="综合健康评分" size="small" style={{ height: '100%' }}>
            <div style={{ textAlign: 'center' }}>
              <Progress
                type="dashboard"
                percent={overallScore}
                strokeColor={scoreColor}
                format={(p) => (
                  <span className="num" style={{ fontSize: 28, fontWeight: 700 }}>
                    {p}
                  </span>
                )}
                size={120}
              />
            </div>
          </Card>
        </Col>
        <Col span={8}>
          <Card className="gojira-card" bordered={false} title="API 用量（今日）" size="small" style={{ height: '100%' }}>
            {apiUsage ? (
              <Space direction="vertical" style={{ width: '100%' }} size="small">
                <Statistic title="调用次数" value={apiUsage.today.total_calls} />
                <Statistic
                  title="缓存命中率"
                  value={apiUsage.today.cache_hit_rate}
                  suffix="%"
                  precision={1}
                />
                <Statistic
                  title="月度预算"
                  value={apiUsage.month.budget_used_pct}
                  suffix="%"
                  precision={1}
                />
                <Progress
                  percent={apiUsage.month.budget_used_pct}
                  size="small"
                  status={apiUsage.month.budget_used_pct > 80 ? 'exception' : 'active'}
                />
              </Space>
            ) : (
              <Text type="secondary">暂无数据</Text>
            )}
          </Card>
        </Col>
        <Col span={8}>
          <Card className="gojira-card" bordered={false} title="死信队列" size="small" style={{ height: '100%' }}>
            {deadLetterStats ? (
              <Space direction="vertical" style={{ width: '100%' }} size="small">
                <Space wrap>
                  <Tag color="orange">待处理 {deadLetterStats.pending}</Tag>
                  <Tag color="blue">重试中 {deadLetterStats.retrying}</Tag>
                  <Tag color="red">已耗尽 {deadLetterStats.exhausted}</Tag>
                  <Tag color="green">已解决 {deadLetterStats.resolved}</Tag>
                </Space>
                {deadLetterStats.total > 0 ? (
                  <Text type="warning">
                    <WarningOutlined /> 共 <span className="num">{deadLetterStats.total}</span> 条记录
                  </Text>
                ) : (
                  <Text type="success">
                    <CheckCircleOutlined /> 无异常记录
                  </Text>
                )}
              </Space>
            ) : (
              <Text type="secondary">暂无数据</Text>
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        {DATA_TYPES.map((dtype) => {
          const h = health?.[dtype];
          const s = status?.[dtype];
          const fresh = h?.fresh ? 'fresh' : h?.latest_date ? 'stale' : 'missing';
          return (
            <Col span={6} key={dtype}>
              <Card
                className="gojira-card"
                bordered={false}
                title={
                  <Space>
                    {DATA_TYPE_ICONS[dtype]} {DATA_TYPE_LABELS[dtype]}
                  </Space>
                }
                size="small"
                style={{ height: '100%' }}
                extra={
                  <Button
                    size="small"
                    icon={<CloudSyncOutlined />}
                    onClick={() => onSync()}
                  >
                    同步
                  </Button>
                }
              >
                <Space direction="vertical" style={{ width: '100%' }} size="small">
                  <div>
                    <FreshnessDot freshness={fresh} />
                    <Text>{FRESHNESS_LABELS[fresh]}</Text>
                    {h?.latest_date && (
                      <Text
                        type="secondary"
                        style={{ marginLeft: 8, fontSize: 'var(--fs-xs)' }}
                      >
                        {h.latest_date}
                      </Text>
                    )}
                  </div>
                  <Statistic title="总记录" value={s?.total_records ?? 0} />
                  <Statistic title="覆盖股票" value={h?.stocks ?? 0} />
                </Space>
              </Card>
            </Col>
          );
        })}
      </Row>

      <div style={{ textAlign: 'center' }}>{RefreshBtn}</div>
    </div>
  );
}
