import { useCallback, useEffect, useState } from 'react';
import { Alert, Card, Col, Progress, Row, Space, Spin, Statistic, Typography } from 'antd';
import { ReloadOutlined, WarningOutlined, CheckCircleOutlined } from '@ant-design/icons';

import { fetchDataQuality } from '../../api/client';
import type { DataQualityResponse } from '../../api/types';
import { DATA_TYPE_LABELS, DATA_TYPE_ICONS, DATA_TYPE_COLORS, FRESHNESS_LABELS, FRESHNESS_COLORS, type DataTypeKey } from './constants';

interface DataTypeQuality {
  completeness_rate: number;
  freshness: 'fresh' | 'stale' | 'missing';
  gap_count: number;
  anomaly_count: number;
  validation_pass_rate: number;
  details: {
    total_stocks: number;
    covered_stocks: number;
    latest_date: string | null;
    earliest_date: string | null;
  };
}

const { Text } = Typography;

interface Props {
  refreshKey: number;
}

export default function DataQualityPanel({ refreshKey }: Props) {
  const [quality, setQuality] = useState<DataQualityResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchDataQuality();
      setQuality(data);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load, refreshKey]);

  if (loading && !quality) {
    return <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>;
  }

  if (!quality) {
    return <Card><Text type="secondary">无法加载数据质量信息</Text></Card>;
  }

  const scoreColor = quality.overall_score >= 80 ? '#52c41a' : quality.overall_score >= 50 ? '#faad14' : '#ff4d4f';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Row gutter={16}>
        <Col span={8}>
          <Card>
            <div style={{ textAlign: 'center' }}>
              <Progress
                type="dashboard"
                percent={quality.overall_score}
                strokeColor={scoreColor}
                format={(p) => <span style={{ fontSize: 28, fontWeight: 700 }}>{p}</span>}
                size={140}
              />
              <div style={{ marginTop: 8 }}><Text type="secondary">综合质量评分</Text></div>
            </div>
          </Card>
        </Col>
        <Col span={16}>
          <Card title="改进建议" size="small" extra={<a onClick={load}><ReloadOutlined /> 刷新</a>}>
            {quality.recommendations.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {quality.recommendations.map((rec: string, i: number) => (
                  <Alert
                    key={i}
                    message={rec}
                    type={rec.includes('缺失') || rec.includes('立即') ? 'error' : rec.includes('较旧') || rec.includes('缺口') ? 'warning' : 'info'}
                    showIcon
                    icon={rec.includes('缺失') ? <WarningOutlined /> : <CheckCircleOutlined />}
                  />
                ))}
              </div>
            ) : (
              <Text type="success"><CheckCircleOutlined /> 数据质量良好，暂无改进建议</Text>
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        {Object.entries(quality.data_types).map(([dtype, rawQ]) => {
          const q = rawQ as DataTypeQuality;
          return (
          <Col span={6} key={dtype}>
            <Card
              title={<Space>{DATA_TYPE_ICONS[dtype as DataTypeKey]} {DATA_TYPE_LABELS[dtype as DataTypeKey]}</Space>}
              size="small"
            >
              <Space orientation="vertical" style={{ width: '100%' }}>
                <div>
                  <Text type="secondary">完整性</Text>
                  <Progress
                    percent={Math.round(q.completeness_rate * 100)}
                    size="small"
                    strokeColor={DATA_TYPE_COLORS[dtype as DataTypeKey]}
                  />
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {q.details.covered_stocks} / {q.details.total_stocks} 只
                  </Text>
                </div>
                <div>
                  <span style={{
                    display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
                    backgroundColor: FRESHNESS_COLORS[q.freshness], marginRight: 6,
                  }} />
                  <Text>{FRESHNESS_LABELS[q.freshness]}</Text>
                  {q.details.latest_date && (
                    <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>{q.details.latest_date}</Text>
                  )}
                </div>
                <Statistic title="缺口数" value={q.gap_count} />
                <Statistic title="异常数" value={q.anomaly_count} />
                <Statistic
                  title="验证通过率"
                  value={q.validation_pass_rate * 100}
                  suffix="%"
                  precision={1}
                />
              </Space>
            </Card>
          </Col>
          );
        })}
      </Row>
    </div>
  );
}
