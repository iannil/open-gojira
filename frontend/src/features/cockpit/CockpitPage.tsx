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
  DollarOutlined,
  FileTextOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons';

import { fetchCockpit } from '../../api/client';
import { getResearchHealth } from '../../api/research';
import type {
  CockpitDraft,
  CockpitHoldingItem,
  CockpitReportItem,
  CockpitAlertV2,
} from '../../api/types';
import PageHeader from '../../components/primitives/PageHeader';
import PageSection from '../../components/primitives/PageSection';

const { Text } = Typography;

const REC_COLORS: Record<string, string> = {
  BUY: 'success', HOLD: 'warning', PASS: 'default', SELL: 'error', TRIM: 'warning',
};
const PIPELINE_LABELS: Record<string, string> = {
  deep_research: '深度研究', thesis_tracker: '论文追踪', news_pulse: '异动归因',
  earnings_review: '财报精读', quality_screen: '质量筛选',
};
const SEVERITY_COLORS: Record<string, string> = {
  critical: 'error', warning: 'warning', info: 'blue',
};
const FUNNEL: { key: string; label: string }[] = [
  { key: 'universe', label: 'universe' },
  { key: 'watchlist', label: 'watchlist' },
  { key: 'researched', label: 'researched' },
  { key: 'candidate', label: 'candidate' },
  { key: 'holding', label: 'holding' },
  { key: 'exited', label: 'exited' },
];

function fmt(n: number | null | undefined, digits = 2): string {
  return n === null || n === undefined ? '—' : n.toFixed(digits);
}

export default function CockpitPage() {
  const cockpitQuery = useQuery({
    queryKey: ['cockpit', 'v2'],
    queryFn: fetchCockpit,
    refetchInterval: 30_000,
  });
  const healthQuery = useQuery({
    queryKey: ['research', 'health'],
    queryFn: getResearchHealth,
    refetchInterval: 60_000,
  });

  const c = cockpitQuery.data;
  const health = healthQuery.data;
  const counts = c?.pipeline_counts ?? {};
  const summary = c?.portfolio.summary ?? {};

  const spendPct = useMemo(() => {
    if (!health) return 0;
    return Math.min(100, (health.spend.total_usd / health.spend.hard_cap_usd) * 100);
  }, [health]);

  return (
    <div>
      <PageHeader
        title="Gojira v2 — 主看板"
        enLabel="Cockpit"
        purpose="信号优先 · 双引擎(价值复利 + 产业链卡点) · 自动驾驶"
        actions={
          <Space>
            <Link to="/reports"><Button icon={<FileTextOutlined />}>研究报告</Button></Link>
            <Link to="/data-management"><Button icon={<ReloadOutlined />}>数据同步</Button></Link>
          </Space>
        }
      />

      {/* ── 应用内告警 banner ──────────────────────────────────────── */}
      {c && c.alerts.critical_count > 0 && (
        <Alert
          style={{ marginBottom: 16 }}
          type="error"
          showIcon
          message={`${c.alerts.critical_count} 条未解决的严重告警`}
          description={c.alerts.items.filter((a) => a.severity === 'critical').slice(0, 3).map((a) => a.message).join('；')}
        />
      )}

      {/* ── 系统状态 ──────────────────────────────────────────────── */}
      <PageSection title="系统状态">
        <Row gutter={16}>
          <Col span={6}>
            <Card>
              <Statistic title="月度 LLM 成本" value={health?.spend.total_usd ?? 0} precision={2}
                prefix={<DollarOutlined />} suffix={`/ $${health?.spend.hard_cap_usd ?? 150}`} />
              <Progress percent={spendPct} size="small"
                status={health?.spend.over_hard ? 'exception' : health?.spend.over_soft ? 'active' : 'normal'} />
            </Card>
          </Col>
          <Col span={6}>
            <Card><Statistic title="观察池" value={counts.watchlist ?? 0} prefix={<SearchOutlined />} />
              <Text type="secondary">待深度研究</Text></Card>
          </Col>
          <Col span={6}>
            <Card><Statistic title="候选池" value={counts.candidate ?? 0} valueStyle={{ color: '#52c41a' }} />
              <Text type="secondary">通过镜子测试</Text></Card>
          </Col>
          <Col span={6}>
            <Card><Statistic title="持仓" value={counts.holding ?? 0} />
              <Text type="secondary">thesis_tracker 监控中</Text></Card>
          </Col>
        </Row>
      </PageSection>

      {/* ── 顶部：待办信号 (Drafts 待审批) ─────────────────────────── */}
      <PageSection title={`🔔 待办信号 — ${c?.drafts_pending_count ?? 0} 个待审批 Draft`}>
        <Card>
          {!c || c.drafts.length === 0 ? (
            <Empty description={
              <Space direction="vertical">
                <Text type="secondary">暂无待审批 Draft</Text>
                <Link to="/drafts"><Button type="link" size="small">查看所有 Drafts</Button></Link>
              </Space>
            } />
          ) : (
            <Table<CockpitDraft> size="small" dataSource={c.drafts} rowKey="id" pagination={{ pageSize: 8, size: 'small' }}
              columns={[
                { title: '股票', dataIndex: 'code', render: (code: string) => <Link to={`/stock/${code}`}>{code}</Link> },
                { title: '方向', dataIndex: 'side', render: (s: string) => <Tag color={s === 'BUY' ? 'success' : 'error'}>{s}</Tag> },
                { title: '关卡', dataIndex: 'step_kind' },
                { title: '建议量', dataIndex: 'suggested_quantity', render: (q: number | null) => q ?? '—' },
                { title: '理由', dataIndex: 'reason', ellipsis: true },
                { title: '操作', key: 'act', render: () => <Link to="/drafts"><Button size="small" type="link">审批</Button></Link> },
              ]} />
          )}
        </Card>
      </PageSection>

      {/* ── 中部：持仓概览 ─────────────────────────────────────────── */}
      <PageSection title="📊 持仓概览">
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={6}><Card><Statistic title="持仓数" value={(summary.position_count as number) ?? 0} /></Card></Col>
          <Col span={6}><Card><Statistic title="组合市值" value={(summary.total_value as number) ?? 0} precision={0} prefix="¥" /></Card></Col>
          <Col span={6}><Card><Statistic title="累计盈亏%" value={(summary.total_pnl_pct as number) ?? 0} precision={2} suffix="%"
            valueStyle={{ color: ((summary.total_pnl_pct as number) ?? 0) >= 0 ? '#cf1322' : '#3f8600' }} /></Card></Col>
          <Col span={6}><Card><Statistic title="现金占比" value={(summary.cash_ratio_pct as number) ?? 0} precision={1} suffix="%" /></Card></Col>
        </Row>
        <Card>
          {!c || c.portfolio.holdings.length === 0 ? (
            <Empty description="暂无持仓（v2 持仓来自 CSV 导入 / 手动录入）" />
          ) : (
            <Table<CockpitHoldingItem> size="small" dataSource={c.portfolio.holdings} rowKey={(h) => h.stock_code} pagination={false}
              columns={[
                { title: '股票', dataIndex: 'stock_code', render: (code: string) => <Link to={`/stock/${code}`}>{code}</Link> },
                { title: '数量', dataIndex: 'quantity' },
                { title: '成本', dataIndex: 'buy_price', render: (p: number) => fmt(p) },
                { title: '现值', dataIndex: 'current_value', render: (v: number | null) => v === null ? '—' : fmt(v, 0) },
                { title: '盈亏%', dataIndex: 'pnl_pct', render: (p: number | null) => p === null || p === undefined ? '—' :
                  <Text style={{ color: p >= 0 ? '#cf1322' : '#3f8600' }}>{fmt(p)}%</Text> },
                { title: '权重%', dataIndex: 'weight_pct', render: (w: number | null) => w === null || w === undefined ? '—' : fmt(w, 1) },
              ]} />
          )}
        </Card>
      </PageSection>

      {/* ── 底部：候选漏斗 (lifecycle 计数) ────────────────────────── */}
      <PageSection title="🎯 候选漏斗">
        <Card>
          <Row gutter={8} align="middle">
            {FUNNEL.map((s, i) => (
              <Col key={s.key} flex="auto">
                <Statistic title={s.label} value={counts[s.key] ?? 0} />
                {i < FUNNEL.length - 1 && <span style={{ color: '#aaa' }}>→</span>}
              </Col>
            ))}
          </Row>
          <Text type="secondary" style={{ fontSize: 12 }}>
            决策 7-9：观察池 30-50 / 候选池 3-5 / 30 天缓存 / 单关卡 Draft 审批
          </Text>
        </Card>
      </PageSection>

      {/* ── 最近研究报告 ──────────────────────────────────────────── */}
      <PageSection title="📄 最近研究报告">
        <Card>
          {!c || c.recent_reports.length === 0 ? (
            <Empty description={<Text type="secondary">还没有研究报告 — 去 <Link to="/universe">股票池</Link> 触发深度研究</Text>} />
          ) : (
            <Table<CockpitReportItem> size="small" dataSource={c.recent_reports} rowKey="id" pagination={{ pageSize: 5 }}
              columns={[
                { title: '股票', dataIndex: 'stock_code', render: (code: string) => <Link to={`/stock/${code}`}>{code}</Link> },
                { title: 'Pipeline', dataIndex: 'pipeline_type', render: (pt: string) => <Tag>{PIPELINE_LABELS[pt] ?? pt}</Tag> },
                { title: '评分', dataIndex: 'overall_score', render: (s: number | null) => s !== null ?
                  <Badge count={s.toFixed(1)} color={s >= 4 ? '#52c41a' : s >= 3 ? '#faad14' : '#ff4d4f'} /> : <Text type="secondary">—</Text> },
                { title: '建议', dataIndex: 'recommendation', render: (r: string | null) => r ? <Tag color={REC_COLORS[r]}>{r}</Tag> : <Text type="secondary">—</Text> },
                { title: '证据', dataIndex: 'evidence_grade', render: (g: string | null) => g ? <Tag color={g === 'A' ? 'success' : g === 'B' ? 'warning' : 'default'}>{g}</Tag> : null },
                { title: '生成时间', dataIndex: 'created_at', render: (ts: string | null) => ts ? new Date(ts).toLocaleString('zh-CN') : null },
              ]} />
          )}
        </Card>
      </PageSection>

      {/* ── 应用内告警列表 ────────────────────────────────────────── */}
      {c && c.alerts.items.length > 0 && (
        <PageSection title={`⚠️ 系统告警（${c.alerts.items.length}）`}>
          <Card>
            <Table<CockpitAlertV2> size="small" dataSource={c.alerts.items} rowKey="id" pagination={false}
              columns={[
                { title: '级别', dataIndex: 'severity', render: (s: string) => <Tag color={SEVERITY_COLORS[s] ?? 'default'}>{s}</Tag> },
                { title: '类别', dataIndex: 'category' },
                { title: '消息', dataIndex: 'message', ellipsis: true },
                { title: '时间', dataIndex: 'created_at', render: (ts: string | null) => ts ? new Date(ts).toLocaleString('zh-CN') : null },
              ]} />
          </Card>
        </PageSection>
      )}
    </div>
  );
}
