import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Empty,
  Progress,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import {
  AlertOutlined,
  BellOutlined,
  DollarOutlined,
  FileTextOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons';

import {
  getResearchHealth,
  listRecentReports,
  type PipelineType,
  type Recommendation,
} from '../../api/research';
import PageHeader from '../../components/primitives/PageHeader';
import PageSection from '../../components/primitives/PageSection';

const { Text } = Typography;

// ── Recommendation tag colors ────────────────────────────────────────────

const REC_COLORS: Record<Recommendation, string> = {
  BUY: 'success',
  HOLD: 'warning',
  PASS: 'default',
  SELL: 'error',
  TRIM: 'warning',
};

const PIPELINE_LABELS: Record<PipelineType, string> = {
  deep_research: '深度研究',
  thesis_tracker: '论文追踪',
  news_pulse: '异动归因',
  earnings_review: '财报精读',
  quality_screen: '质量筛选',
};

// ── Page ─────────────────────────────────────────────────────────────────

export default function CockpitPage() {
  const healthQuery = useQuery({
    queryKey: ['research', 'health'],
    queryFn: getResearchHealth,
    refetchInterval: 60_000,
  });

  const reportsQuery = useQuery({
    queryKey: ['research', 'reports', 'recent'],
    queryFn: () => listRecentReports(undefined, 10),
    refetchInterval: 60_000,
  });

  const health = healthQuery.data;
  const reports = reportsQuery.data ?? [];

  const spendPct = useMemo(() => {
    if (!health) return 0;
    return Math.min(100, (health.spend.total_usd / health.spend.hard_cap_usd) * 100);
  }, [health]);

  return (
    <div>
      <PageHeader
        title="Gojira v2 — 主看板"
        enLabel="Cockpit"
        purpose="信号优先 · 规则+LLM 混合研究 · 自动驾驶"
        actions={
          <Space>
            <Link to="/reports">
              <Button icon={<FileTextOutlined />}>研究报告</Button>
            </Link>
            <Link to="/data-management">
              <Button icon={<ReloadOutlined />}>数据同步</Button>
            </Link>
          </Space>
        }
      />

      {/* ── Status Overview ────────────────────────────────────────── */}
      <PageSection title="系统状态">
        <Row gutter={16}>
          <Col span={6}>
            <Card>
              <Statistic
                title="月度 LLM 成本"
                value={health?.spend.total_usd ?? 0}
                precision={2}
                prefix={<DollarOutlined />}
                suffix={`/ $${health?.spend.hard_cap_usd ?? 150}`}
              />
              <Progress
                percent={spendPct}
                status={
                  health?.spend.over_hard
                    ? 'exception'
                    : health?.spend.over_soft
                      ? 'active'
                      : 'normal'
                }
                size="small"
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="观察池"
                value={health?.lifecycle_counts.watchlist ?? 0}
                prefix={<SearchOutlined />}
              />
              <Text type="secondary">待深度研究</Text>
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="候选池"
                value={health?.lifecycle_counts.candidate ?? 0}
                prefix={<AlertOutlined />}
                valueStyle={{ color: '#52c41a' }}
              />
              <Text type="secondary">通过镜子测试</Text>
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="持仓"
                value={health?.lifecycle_counts.holding ?? 0}
                prefix={<BellOutlined />}
              />
              <Text type="secondary">thesis_tracker 监控中</Text>
            </Card>
          </Col>
        </Row>

        {(health?.spend.over_soft || health?.spend.over_hard) && (
          <Alert
            style={{ marginTop: 16 }}
            type={health.spend.over_hard ? 'error' : 'warning'}
            message={
              health.spend.over_hard
                ? `LLM 成本硬熔断：$${health.spend.total_usd.toFixed(2)} / $${health.spend.hard_cap_usd}`
                : `LLM 成本软告警：$${health.spend.total_usd.toFixed(2)} / $${health.spend.soft_warning_usd}`
            }
            description={
              health.spend.over_hard
                ? '非关键 Pipeline 已暂停。持仓监控（thesis_tracker / news_pulse）继续运行。'
                : '建议关注 Pipeline 成本趋势。'
            }
            showIcon
          />
        )}
      </PageSection>

      {/* ── Signals (待办) ────────────────────────────────────────── */}
      <PageSection title="🔔 待办信号（Drafts 待审批）">
        <Card>
          <Empty
            description={
              <Space direction="vertical">
                <Text type="secondary">暂无待审批 Draft</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  Pipeline 进入 Phase 5 后，候选股票价格进入安全边际区间会自动生成 BUY Draft。
                  SELL Draft 由 thesis_tracker / news_pulse 触发。
                </Text>
                <Link to="/drafts">
                  <Button type="link" size="small">查看所有 Drafts</Button>
                </Link>
              </Space>
            }
          />
        </Card>
      </PageSection>

      {/* ── Recent Reports ────────────────────────────────────────── */}
      <PageSection title="📄 最近研究报告">
        <Card>
          {reports.length === 0 ? (
            <Empty
              description={
                <Space direction="vertical">
                  <Text type="secondary">还没有任何研究报告</Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    去 <Link to="/universe">股票池</Link> 找一只股票触发深度研究。
                  </Text>
                </Space>
              }
            />
          ) : (
            <Table
              size="small"
              dataSource={reports}
              rowKey="id"
              pagination={{ pageSize: 5 }}
              columns={[
                {
                  title: '股票',
                  dataIndex: 'stock_code',
                  render: (code: string) => (
                    <Link to={`/stock/${code}`}>{code}</Link>
                  ),
                },
                {
                  title: 'Pipeline',
                  dataIndex: 'pipeline_type',
                  render: (pt: PipelineType) => (
                    <Tag>{PIPELINE_LABELS[pt] ?? pt}</Tag>
                  ),
                },
                {
                  title: '评分',
                  dataIndex: 'overall_score',
                  render: (score: number | null) =>
                    score !== null ? (
                      <Badge
                        count={score.toFixed(1)}
                        color={
                          score >= 4
                            ? '#52c41a'
                            : score >= 3
                              ? '#faad14'
                              : '#ff4d4f'
                        }
                      />
                    ) : (
                      <Text type="secondary">—</Text>
                    ),
                },
                {
                  title: '建议',
                  dataIndex: 'recommendation',
                  render: (rec: Recommendation | null) =>
                    rec ? <Tag color={REC_COLORS[rec]}>{rec}</Tag> : <Text type="secondary">—</Text>,
                },
                {
                  title: '证据',
                  dataIndex: 'evidence_grade',
                  render: (g: string | null) =>
                    g ? <Tag color={g === 'A' ? 'success' : g === 'B' ? 'warning' : 'default'}>{g}</Tag> : null,
                },
                {
                  title: '状态',
                  dataIndex: 'status',
                  render: (s: string) => {
                    const color =
                      s === 'completed'
                        ? 'success'
                        : s === 'rejected'
                          ? 'error'
                          : s === 'conflict'
                            ? 'warning'
                            : 'default';
                    return <Tag color={color}>{s}</Tag>;
                  },
                },
                {
                  title: '生成时间',
                  dataIndex: 'created_at',
                  render: (ts: string | null) =>
                    ts ? new Date(ts).toLocaleString('zh-CN') : null,
                },
              ]}
            />
          )}
        </Card>
      </PageSection>

      {/* ── Lifecycle Funnel ─────────────────────────────────────── */}
      <PageSection title="🎯 候选漏斗">
        <Card>
          <Row gutter={16} align="middle">
            <Col span={3}>
              <Statistic title="universe" value={health?.lifecycle_counts.universe ?? 0} />
            </Col>
            <Col span={1}>→</Col>
            <Col span={4}>
              <Statistic title="watchlist" value={health?.lifecycle_counts.watchlist ?? 0} />
            </Col>
            <Col span={1}>→</Col>
            <Col span={4}>
              <Statistic title="researched" value={health?.lifecycle_counts.researched ?? 0} />
            </Col>
            <Col span={1}>→</Col>
            <Col span={3}>
              <Statistic title="candidate" value={health?.lifecycle_counts.candidate ?? 0} />
            </Col>
            <Col span={1}>→</Col>
            <Col span={3}>
              <Statistic title="holding" value={health?.lifecycle_counts.holding ?? 0} />
            </Col>
            <Col span={1}>→</Col>
            <Col span={2}>
              <Statistic title="exited" value={health?.lifecycle_counts.exited ?? 0} />
            </Col>
          </Row>
          <div style={{ marginTop: 16 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              决策 7-9（redesign-decisions-v2.md）：观察池 30-50 / 候选池 3-5 / 30 天缓存 / 单关卡 Draft 审批
            </Text>
          </div>
        </Card>
      </PageSection>

      {/* ── Quick Actions ────────────────────────────────────────── */}
      <PageSection title="⚡ 快速操作">
        <Space wrap>
          <Link to="/universe">
            <Button>浏览股票池</Button>
          </Link>
          <Link to="/reports">
            <Button icon={<FileTextOutlined />}>所有报告</Button>
          </Link>
          <Link to="/drafts">
            <Button>Drafts（待 Phase 5 实现）</Button>
          </Link>
          <Link to="/scheduler">
            <Button>定时任务</Button>
          </Link>
          <Link to="/monitoring">
            <Button>系统监控</Button>
          </Link>
        </Space>
      </PageSection>
    </div>
  );
}
