import { useMemo } from 'react';
import { Card, Col, Row, Spin, Statistic, Tag, Button, Space, Typography, Progress } from 'antd';
import { CloudSyncOutlined, ReloadOutlined, WarningOutlined, CheckCircleOutlined } from '@ant-design/icons';

import { useDataStatus } from './hooks/useDataStatus';
import { DATA_TYPES, DATA_TYPE_LABELS, DATA_TYPE_ICONS, FRESHNESS_LABELS, FRESHNESS_COLORS } from './constants';

const { Text } = Typography;

interface Props {
  refreshKey: number;
  onSync: (dataType: string) => void;
}

function FreshnessDot({ freshness }: { freshness: string }) {
  const color = FRESHNESS_COLORS[freshness] || '#d9d9d9';
  return (
    <span style={{
      display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
      backgroundColor: color, marginRight: 6,
    }} />
  );
}

export default function DataHealthDashboard({ refreshKey, onSync }: Props) {
  const { status, health, apiUsage, deadLetterStats, loading, refresh } = useDataStatus(refreshKey);

  const overallScore = useMemo(() => {
    if (!health || !status) return 0;
    let total = 0;
    for (const dtype of DATA_TYPES) {
      const h = health[dtype];
      const s = status[dtype];
      if (!h) continue;
      const freshScore = h.fresh ? 40 : 20;
      const coverageScore = s && s.stock_count > 0 ? Math.min((s.stock_count / Math.max(s.total_records, 1)) * 30, 30) : 0;
      const volumeScore = s && s.total_records > 0 ? 30 : 0;
      total += freshScore + coverageScore + volumeScore;
    }
    return Math.round(total / DATA_TYPES.length);
  }, [health, status]);

  const scoreColor = overallScore >= 80 ? '#52c41a' : overallScore >= 50 ? '#faad14' : '#ff4d4f';

  if (loading && !status) {
    return <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Row gutter={16}>
        <Col span={8}>
          <Card title="综合健康评分" size="small" style={{ height: '100%' }}>
            <div style={{ textAlign: 'center' }}>
              <Progress
                type="dashboard"
                percent={overallScore}
                strokeColor={scoreColor}
                format={(p) => <span style={{ fontSize: 28, fontWeight: 700 }}>{p}</span>}
                size={120}
              />
            </div>
          </Card>
        </Col>
        <Col span={8}>
          <Card title="API 用量（今日）" size="small" style={{ height: '100%' }}>
            {apiUsage ? (
              <Space orientation="vertical" style={{ width: '100%' }} size="small">
                <Statistic title="调用次数" value={apiUsage.today.total_calls} />
                <Statistic title="缓存命中率" value={apiUsage.today.cache_hit_rate} suffix="%" precision={1} />
                <Statistic title="月度预算" value={apiUsage.month.budget_used_pct} suffix="%" precision={1} />
                <Progress percent={apiUsage.month.budget_used_pct} size="small" status={apiUsage.month.budget_used_pct > 80 ? 'exception' : 'active'} />
              </Space>
            ) : <Text type="secondary">暂无数据</Text>}
          </Card>
        </Col>
        <Col span={8}>
          <Card title="死信队列" size="small" style={{ height: '100%' }}>
            {deadLetterStats ? (
              <Space orientation="vertical" style={{ width: '100%' }} size="small">
                <Space wrap>
                  <Tag color="orange">待处理 {deadLetterStats.pending}</Tag>
                  <Tag color="blue">重试中 {deadLetterStats.retrying}</Tag>
                  <Tag color="red">已耗尽 {deadLetterStats.exhausted}</Tag>
                  <Tag color="green">已解决 {deadLetterStats.resolved}</Tag>
                </Space>
                {deadLetterStats.total > 0 && (
                  <Text type="warning"><WarningOutlined /> 共 {deadLetterStats.total} 条记录</Text>
                )}
                {deadLetterStats.total === 0 && (
                  <Text type="success"><CheckCircleOutlined /> 无异常记录</Text>
                )}
              </Space>
            ) : <Text type="secondary">暂无数据</Text>}
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        {DATA_TYPES.map((dtype) => {
          const h = health?.[dtype];
          const s = status?.[dtype];
          const fresh = h?.fresh ? 'fresh' : (h?.latest_date ? 'stale' : 'missing');
          return (
            <Col span={6} key={dtype}>
              <Card
                title={<Space>{DATA_TYPE_ICONS[dtype]} {DATA_TYPE_LABELS[dtype]}</Space>}
                size="small"
                style={{ height: '100%' }}
                extra={
                  <Button size="small" icon={<CloudSyncOutlined />} onClick={() => onSync(dtype)}>
                    同步
                  </Button>
                }
              >
                <Space orientation="vertical" style={{ width: '100%' }} size="small">
                  <div>
                    <FreshnessDot freshness={fresh} />
                    <Text>{FRESHNESS_LABELS[fresh]}</Text>
                    {h?.latest_date && <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>{h.latest_date}</Text>}
                  </div>
                  <Statistic title="总记录" value={s?.total_records ?? 0} />
                  <Statistic title="覆盖股票" value={h?.stocks ?? 0} />
                </Space>
              </Card>
            </Col>
          );
        })}
      </Row>

      <div style={{ textAlign: 'center' }}>
        <Button icon={<ReloadOutlined />} onClick={refresh}>刷新状态</Button>
      </div>
    </div>
  );
}
