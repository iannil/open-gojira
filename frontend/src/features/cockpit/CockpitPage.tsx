/**
 * Cockpit — autopilot main dashboard.
 *
 * Phase 12a: data layer migrated to TanStack Query. Visual structure and
 * inline sub-components preserved — Phase 12b will split into separate
 * component files + apply new visual primitives.
 *
 * Reads `GET /api/cockpit` (one aggregator) + `GET /themes/exposure`
 * (slow, separate) and renders the 10-card HUD:
 *   ① Cashflow goal progress / weighted DYR / portfolio value
 *   ② Today's BUY/SELL drafts (with one-click execute / cancel)
 *   ③ Market cycle + temperature
 *   ④ Theme exposure drift
 *   ⑤ Rebalance suggestions
 *   ⑥ Dividend projection
 *   ⑦ Thesis variable alerts
 *   ⑧ Four-quadrant breakdown pie
 *   ⑨ Unacked alerts list
 *   ⑩ Holdings compact + active plans + pending corp actions
 */

import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Progress,
  Row,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import ReactECharts from 'echarts-for-react';

import echarts from '../../lib/echarts';
import DisciplineChecklistModal from '../../components/DisciplineChecklistModal';
import DraftAvailableCell from '../../components/DraftAvailableCell';
import { PendingCorpActionsCard } from '../../components/PendingCorpActionsCard';
import PendingClaimVariablesBadge from './PendingClaimVariablesBadge';
import { PageHeader } from '../../components/primitives';
import {
  useCancelDraftMutation,
  useExecuteDraftMutation,
} from '../drafts/useDraftMutations';
import { useCashflowGoalQuery, useCockpitQuery, useCriticalAlertsQuery, useThemeExposureQuery } from './useCockpitQueries';
import { useUpdateCashflowGoalMutation } from './useCockpitMutations';
import type { CashflowGoalUpdate } from '../../api/types';
import type {
  CockpitDraft,
  CockpitHoldingItem,
  CockpitQuadrant,
  CockpitResponse,
  RebalanceSuggestion,
  SerenityCockpitSummary,
  ThemeExposureAnalysis,
  ThemeExposureItem,
} from '../../api/types';

const { Title, Text } = Typography;

// ── helpers ───────────────────────────────────────────────────────────

function formatCurrency(value: number | null | undefined, currency = 'CNY'): string {
  if (value == null) return '—';
  const symbol = currency === 'CNY' ? '¥' : currency;
  return `${symbol}${new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value)}`;
}

function formatPct(decimal: number | null | undefined, fractionDigits = 2): string {
  if (decimal == null) return '—';
  return `${(decimal * 100).toFixed(fractionDigits)}%`;
}

function progressColor(progress: number): string {
  if (progress >= 1) return 'var(--green-600)';
  if (progress >= 0.7) return 'var(--primary-600)';
  if (progress >= 0.3) return 'var(--amber-600)';
  return 'var(--red-600)';
}

const QUADRANT_LABEL: Record<string, string> = {
  procyclical: '顺周期',
  countercyclical: '逆周期',
  distressed_reversal: '困境反转',
  financial: '金融',
  unlabeled: '未分类',
};

const DRAFT_SIDE_LABEL: Record<string, string> = { BUY: '买入', SELL: '卖出' };

const STEP_KIND_LABEL: Record<string, string> = {
  buy_ladder: '买入档位',
  sell_ladder: '卖出档位',
  rebalance: '再平衡',
};

const ALERT_LEVEL_LABEL: Record<string, string> = {
  critical: '严重',
  warning: '警告',
  info: '信息',
};

const PLAN_STATUS_LABEL: Record<string, string> = {
  active: '运行中',
  paused: '已暂停',
  archived: '已归档',
};

const QUADRANT_COLOR: Record<string, string> = {
  procyclical: '#4F6D93',
  countercyclical: '#9C5D3A',
  distressed_reversal: '#7B6CA8',
  financial: '#5B8A72',
  unlabeled: '#8C8C8C',
};

// ── sub-components (inline until Phase 12b) ────────────────────────────

function CycleDashboardCard({
  temperature,
  cycle,
}: {
  temperature: number | null | undefined;
  cycle: CockpitResponse['cycle'] | undefined;
}) {
  let tempColor = '#8C8C8C';
  let tempLabel = '未知';
  let tempValue = '—';

  if (temperature != null) {
    tempValue = temperature.toFixed(0);
    if (temperature <= 30) {
      tempColor = 'var(--primary-600)';
      tempLabel = '冷';
    } else if (temperature <= 70) {
      tempColor = 'var(--gray-400)';
      tempLabel = '温';
    } else {
      tempColor = 'var(--red-600)';
      tempLabel = '热';
    }
  }

  const cycleLabels: Record<string, { label: string; color: string }> = {
    extreme_low: { label: '极度低估', color: 'var(--green-600)' },
    low: { label: '低估', color: 'var(--green-500)' },
    mid: { label: '中等', color: 'var(--gray-500)' },
    high: { label: '偏高', color: 'var(--amber-600)' },
    extreme_high: { label: '极度高估', color: 'var(--red-600)' },
  };

  const pos = cycle?.cycle_position
    ? cycleLabels[cycle.cycle_position] ?? { label: cycle.cycle_position, color: 'var(--gray-500)' }
    : null;

  return (
    <Card className="gojira-card" bordered={false} title="市场周期" style={{ marginBottom: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
        <div style={{ textAlign: 'center' }}>
          <div
            style={{
              width: 72,
              height: 72,
              borderRadius: '50%',
              backgroundColor: tempColor,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'white',
              fontWeight: 'bold',
            }}
          >
            <div className="num" style={{ fontSize: 22, lineHeight: 1 }}>{tempValue}</div>
            <div style={{ fontSize: 11 }}>{tempLabel}</div>
          </div>
          <Text type="secondary" style={{ fontSize: 11, marginTop: 4, display: 'block' }}>
            PE 分位
          </Text>
        </div>

        {pos && (
          <div style={{ flex: 1 }}>
            <div style={{ marginBottom: 8 }}>
              <Tag color={pos.color} style={{ fontSize: 14, padding: '2px 12px' }}>
                {pos.label}
              </Tag>
            </div>
            {cycle?.position_advice && (
              <Text style={{ fontSize: 13, display: 'block', marginBottom: 4 }}>
                {cycle.position_advice}
              </Text>
            )}
            {cycle?.position_range && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                建议仓位{' '}
                <span className="num">{(cycle.position_range[0] * 100).toFixed(0)}%</span>–
                <span className="num">{(cycle.position_range[1] * 100).toFixed(0)}%</span>
              </Text>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

function ThemeExposureCard({ data }: { data: ThemeExposureAnalysis | null }) {
  if (!data || !data.exposure || data.exposure.length === 0) {
    return (
      <Card className="gojira-card" bordered={false} title="主题配置" style={{ marginBottom: 0 }}>
        <Empty description="暂无主题配置" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </Card>
    );
  }

  const columns: ColumnsType<ThemeExposureItem> = [
    { title: '主题', dataIndex: 'theme', width: 120 },
    {
      title: '权重%',
      dataIndex: 'weight_pct',
      width: 80,
      align: 'right',
      render: (v: number) => <span className="num">{v.toFixed(1)}%</span>,
    },
    {
      title: '市值',
      dataIndex: 'value',
      width: 100,
      align: 'right',
      render: (v: number) => <span className="num">{v.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}</span>,
    },
    {
      title: '数量',
      dataIndex: 'count',
      width: 60,
      align: 'right',
    },
  ];

  return (
    <Card
      className="gojira-card"
      bordered={false}
      title="主题配置"
      style={{ marginBottom: 0 }}
    >
      <Table dataSource={data.exposure} columns={columns} rowKey="theme" size="small" pagination={false} />
    </Card>
  );
}

function RebalancingSuggestionsCard({ suggestions }: { suggestions: RebalanceSuggestion[] }) {
  if (!suggestions || suggestions.length === 0) {
    return (
      <Card className="gojira-card" bordered={false} title="再平衡建议" style={{ marginBottom: 0 }}>
        <Empty description="暂无再平衡建议" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </Card>
    );
  }

  const columns: ColumnsType<RebalanceSuggestion> = [
    {
      title: '级别',
      dataIndex: 'level',
      width: 80,
      render: (level: string) => {
        const labelMap: Record<string, string> = {
          position: '个股',
          quadrant: '象限',
          theme: '主题',
        };
        return labelMap[level] || level;
      },
    },
    {
      title: '标的',
      width: 100,
      render: (_: unknown, r: RebalanceSuggestion) => {
        if (r.level === 'position' && r.code) {
          return (
            <Link to={`/stock/${r.code}`}>
              <Tag color="blue">{r.code}</Tag>
            </Link>
          );
        }
        if (r.level === 'quadrant' && r.quadrant) return <Tag>{r.quadrant}</Tag>;
        if (r.level === 'theme' && r.theme) return <Tag>{r.theme}</Tag>;
        return '—';
      },
    },
    {
      title: '当前%',
      dataIndex: 'current_pct',
      width: 80,
      align: 'right',
      render: (v: number) => <span className="num">{(v * 100).toFixed(1)}%</span>,
    },
    {
      title: '目标%',
      dataIndex: 'target_pct',
      width: 80,
      align: 'right',
      render: (v: number) => <span className="num">{(v * 100).toFixed(1)}%</span>,
    },
    {
      title: '偏离%',
      dataIndex: 'drift_pct',
      width: 80,
      align: 'right',
      render: (v: number) => {
        const color = Math.abs(v) > 0.05 ? 'var(--red-600)' : 'var(--amber-600)';
        return (
          <span className="num" style={{ color }}>
            {(v * 100).toFixed(1)}%
          </span>
        );
      },
    },
    { title: '建议操作', dataIndex: 'action', width: 120, ellipsis: true },
    {
      title: '优先级',
      dataIndex: 'priority',
      width: 80,
      render: (priority: string) => {
        const colorMap: Record<string, string> = { high: 'red', medium: 'orange', low: 'green' };
        return (
          <Tag color={colorMap[priority] || 'default'} style={{ fontSize: 11 }}>
            {priority}
          </Tag>
        );
      },
    },
  ];

  return (
    <Card className="gojira-card" bordered={false} title={`再平衡建议 (${suggestions.length})`} style={{ marginBottom: 0 }}>
      <Table
        dataSource={suggestions}
        columns={columns}
        rowKey={(r) => `${r.level}-${r.code || r.quadrant || r.theme || ''}-${r.current_pct}`}
        size="small"
        pagination={false}
      />
    </Card>
  );
}

interface GoalFormValues {
  annual_expense: number;
  goal_multiple: number;
  currency: string;
  notes?: string;
  cash_reserve?: number;
}

function GoalEditor({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const goalQ = useCashflowGoalQuery();
  const updateM = useUpdateCashflowGoalMutation();
  const [form] = Form.useForm<GoalFormValues>();

  // Seed form when modal opens with goal data
  const goal = goalQ.data;
  const formReady = open && !!goal;

  if (formReady) {
    form.setFieldsValue({
      annual_expense: goal.annual_expense,
      goal_multiple: goal.goal_multiple,
      currency: goal.currency,
      notes: goal.notes ?? '',
      cash_reserve: goal.cash_reserve ?? 0,
    });
  }

  const handleOk = async () => {
    let values: GoalFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    const payload: CashflowGoalUpdate = {
      annual_expense: values.annual_expense,
      goal_multiple: values.goal_multiple,
      currency: values.currency,
      notes: values.notes || null,
      cash_reserve: values.cash_reserve,
    };
    await updateM.mutateAsync(payload);
    onClose();
  };

  return (
    <Modal
      open={open}
      title="设定现金流目标"
      onCancel={onClose}
      onOk={handleOk}
      okText="保存"
      cancelText="取消"
      confirmLoading={updateM.isPending}
      destroyOnHidden
    >
      {goalQ.isLoading ? (
        <div style={{ textAlign: 'center', padding: 24 }}>
          <Spin />
        </div>
      ) : (
        <Form
          form={form}
          layout="vertical"
          initialValues={{ annual_expense: 0, goal_multiple: 15, currency: 'CNY' }}
        >
          <Form.Item
            label="年度开销"
            name="annual_expense"
            rules={[{ required: true, type: 'number', min: 0 }]}
            extra="日常生活年支出基线（不含投资本金）"
          >
            <InputNumber style={{ width: '100%' }} min={0} step={10000} addonAfter="元" />
          </Form.Item>
          <Form.Item
            label="目标倍数"
            name="goal_multiple"
            rules={[{ required: true, type: 'number', min: 0.01 }]}
            extra="原文建议 10–20×；默认 15×"
          >
            <InputNumber style={{ width: '100%' }} min={1} max={50} step={1} addonAfter="×" />
          </Form.Item>
          <Form.Item label="币种" name="currency">
            <Input maxLength={10} />
          </Form.Item>
          <Form.Item
            label="现金储备"
            name="cash_reserve"
            extra="待入场的现金子弹（元），用于计算空仓比"
          >
            <Space.Compact style={{ width: '100%' }}>
              <InputNumber style={{ flex: 1 }} min={0} step={10000} />
              <Input style={{ width: 32, textAlign: 'center' }} value="元" disabled />
            </Space.Compact>
          </Form.Item>
          <Form.Item label="备注" name="notes">
            <Input.TextArea rows={2} maxLength={500} />
          </Form.Item>
        </Form>
      )}
    </Modal>
  );
}

function GoalNavigator({
  data,
  onEdit,
}: {
  data: CockpitResponse['cashflow'];
  onEdit: () => void;
}) {
  const progress = data.goal_progress ?? 0;
  const progressPct = Math.min(progress * 100, 100);
  const isUnset = data.target_annual_cashflow === 0;
  return (
    <Card
      className="gojira-card"
      bordered={false}
      style={{ marginBottom: 16 }}
      extra={
        <Button size="small" onClick={onEdit}>
          {isUnset ? '设定目标' : '编辑目标'}
        </Button>
      }
    >
      <Row gutter={24} align="middle">
        <Col xs={24} md={10}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            现金流目标进度（<span className="num">{data.goal_multiple}</span>× 年开销）
          </Text>
          <Title level={2} style={{ margin: '4px 0' }}>
            <span className="num">
              {data.goal_progress != null
                ? `${(progress * 100).toFixed(1)}%`
                : '尚未设定目标'}
            </span>
          </Title>
          <Progress percent={progressPct} strokeColor={progressColor(progress)} showInfo={false} />
          <Text type="secondary" style={{ fontSize: 12 }}>
            <span className="num">{formatCurrency(data.annual_passive_cashflow, data.currency)}</span> /{' '}
            <span className="num">{formatCurrency(data.target_annual_cashflow, data.currency)}</span>
          </Text>
        </Col>
        <Col xs={12} md={7}>
          <Statistic
            title="组合加权股息率"
            value={data.weighted_dyr != null ? data.weighted_dyr * 100 : 0}
            precision={2}
            suffix="%"
            styles={{
              content: {
                color:
                  data.weighted_dyr != null && data.weighted_dyr >= 0.045
                    ? 'var(--green-600)'
                    : 'var(--red-600)',
              },
            }}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            目标 4.5% 以上
          </Text>
        </Col>
        <Col xs={12} md={7}>
          <Statistic
            title="组合总值"
            value={data.total_portfolio_value}
            precision={0}
            formatter={(v) => formatCurrency(Number(v), data.currency)}
          />
        </Col>
      </Row>
    </Card>
  );
}

function DraftList({
  drafts,
  onExecute,
  onCancel,
  executePending,
  cancelPending,
}: {
  drafts: CockpitDraft[];
  onExecute: (id: number) => void;
  onCancel: (id: number) => void;
  executePending: boolean;
  cancelPending: boolean;
}) {
  // Cockpit is a HUD — show top 5 by conviction (qiu_score desc, then most
  // recent). Full triage lives at /drafts. Avoids dumping 200+ pending
  // drafts onto the dashboard.
  const DISPLAY_LIMIT = 5;
  const sorted = [...drafts].sort(
    (a, b) => (b.qiu_score ?? 0) - (a.qiu_score ?? 0),
  );
  const visible = sorted.slice(0, DISPLAY_LIMIT);
  const hiddenCount = Math.max(0, drafts.length - DISPLAY_LIMIT);

  const columns: ColumnsType<CockpitDraft> = [
    {
      title: '方向',
      dataIndex: 'side',
      width: 64,
      render: (side: string) => (
        <Tag color={side === 'BUY' ? 'green' : 'red'}>{DRAFT_SIDE_LABEL[side] ?? side}</Tag>
      ),
    },
    {
      title: '标的',
      dataIndex: 'code',
      width: 160,
      render: (code: string, r: CockpitDraft) => (
        <Link to={`/stock/${code}`}>{r.stock_name ? `${r.stock_name} ${code}` : code}</Link>
      ),
    },
    {
      title: '评分',
      dataIndex: 'qiu_score',
      width: 56,
      render: (v: number | null) => v ?? '—',
      sorter: (a: CockpitDraft, b: CockpitDraft) => (a.qiu_score ?? 0) - (b.qiu_score ?? 0),
      defaultSortOrder: 'descend',
    },
    {
      title: '比例',
      width: 100,
      render: (_: unknown, r: CockpitDraft) =>
        r.side === 'BUY'
          ? `+组合 ${formatPct(r.add_pct, 1)}`
          : `−仓位 ${formatPct(r.reduce_pct_of_position, 0)}`,
    },
    { title: '触发原因', dataIndex: 'reason', ellipsis: true },
    {
      title: '可卖份额',
      width: 200,
      render: (_: unknown, r: CockpitDraft) =>
        r.side === 'SELL' ? <DraftAvailableCell code={r.code} /> : '—',
    },
    {
      title: '档位',
      width: 160,
      render: (_: unknown, r: CockpitDraft) => (
        <Space size={4}>
          <Tag>{`${STEP_KIND_LABEL[r.step_kind] ?? r.step_kind}[${r.step_index}]`}</Tag>
          {r.source === 'rebalance' && <Tag color="orange">系统</Tag>}
        </Space>
      ),
    },
    {
      title: '操作',
      width: 170,
      render: (_: unknown, r: CockpitDraft) => (
        <Space size={4}>
          <Button size="small" type="primary" loading={executePending} onClick={() => onExecute(r.id)}>
            标记已成交
          </Button>
          <Button size="small" danger loading={cancelPending} onClick={() => onCancel(r.id)}>
            取消
          </Button>
        </Space>
      ),
    },
  ];
  return (
    <Card
      className="gojira-card"
      bordered={false}
      title={`今日订单草稿 (${drafts.length})`}
      style={{ marginBottom: 16 }}
      extra={
        drafts.length > 0 && (
          <Space>
            <Text type="secondary" style={{ fontSize: 12 }}>
              人工去券商下单，回填后自动登记到持仓
            </Text>
            {hiddenCount > 0 && (
              <Link to="/drafts">
                <Button size="small" type="link">
                  查看全部 <span className="num">{drafts.length}</span> 条 →
                </Button>
              </Link>
            )}
          </Space>
        )
      }
    >
      {drafts.length === 0 ? (
        <Empty description="今日无草稿" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <>
          <Table dataSource={visible} columns={columns} rowKey="id" size="small" pagination={false} />
          {hiddenCount > 0 && (
            <div style={{ textAlign: 'center', marginTop: 8 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                已按 Qiu 评分排序，仅显示前 <span className="num">{DISPLAY_LIMIT}</span> 条 ·{' '}
                <Link to="/drafts">还有 <span className="num">{hiddenCount}</span> 条待处理 →</Link>
              </Text>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

function QuadrantPie({ data }: { data: CockpitQuadrant[] }) {
  const option = useMemo(
    () => ({
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { bottom: 0, type: 'scroll' },
      series: [
        {
          type: 'pie',
          radius: ['40%', '70%'],
          avoidLabelOverlap: true,
          label: { show: false, position: 'center' },
          data: data.map((d) => ({
            value: Math.round(d.value),
            name: QUADRANT_LABEL[d.quadrant] || d.quadrant,
            itemStyle: { color: QUADRANT_COLOR[d.quadrant] || '#A8A29E' },
          })),
        },
      ],
    }),
    [data],
  );

  return (
    <Card className="gojira-card" bordered={false} title="四象限分布">
      {data.length === 0 ? (
        <Empty description="暂无可分配持仓" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <ReactECharts echarts={echarts} option={option} style={{ height: 280 }} />
      )}
    </Card>
  );
}

function AlertsList({ alerts }: { alerts: CockpitResponse['alerts'] }) {
  return (
    <Card className="gojira-card" bordered={false} title={`未确认告警 (${alerts.unacked_count})`}>
      {alerts.items.length === 0 ? (
        <Empty description="一切正常" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <List
          size="small"
          dataSource={alerts.items}
          renderItem={(ev) => (
            <List.Item>
              <List.Item.Meta
                title={
                  <Space>
                    <Tag color={ev.level === 'critical' ? 'red' : 'orange'}>
                      {ALERT_LEVEL_LABEL[ev.level] ?? ev.level}
                    </Tag>
                    {ev.stock_code && <Link to={`/stock/${ev.stock_code}`}>{ev.stock_code}</Link>}
                  </Space>
                }
                description={ev.message}
              />
            </List.Item>
          )}
        />
      )}
    </Card>
  );
}

function HoldingsTable({ items }: { items: CockpitHoldingItem[] }) {
  const columns: ColumnsType<CockpitHoldingItem> = [
    {
      title: '代码',
      dataIndex: 'stock_code',
      width: 100,
      render: (code: string) => <Link to={`/stock/${code}`}>{code}</Link>,
    },
    {
      title: '名称',
      dataIndex: 'stock_name',
      width: 120,
      render: (v: string | null | undefined) => v ?? '—',
    },
    {
      title: '行业',
      dataIndex: 'stock_industry',
      width: 100,
      render: (v: string | null | undefined) => v ?? '—',
    },
    {
      title: '分层',
      dataIndex: 'stock_tier',
      width: 70,
      render: (v: string | null | undefined) => {
        if (!v) return '—';
        return (
          <Tag color={v === 'core' ? 'gold' : 'blue'} style={{ fontSize: 11 }}>
            {v === 'core' ? '核心' : '关注'}
          </Tag>
        );
      },
    },
    {
      title: '仓位 %',
      dataIndex: 'weight_pct',
      width: 90,
      align: 'right',
      render: (v: number | undefined) =>
        v != null ? <span className="num">{v.toFixed(1)}</span> : '—',
    },
    {
      title: '市值',
      dataIndex: 'current_value',
      align: 'right',
      render: (v: number | null) => <span className="num">{formatCurrency(v)}</span>,
    },
  ];
  return (
    <Card className="gojira-card" bordered={false} title={`持仓 (${items.length})`}>
      <Table dataSource={items} columns={columns} rowKey="id" size="small" pagination={false} />
    </Card>
  );
}

function PlansList({ plans }: { plans: CockpitResponse['plans'] }) {
  return (
    <Card
      className="gojira-card"
      bordered={false}
      title={`运行中预案 (${plans.length})`}
      extra={
        <Link to="/plans">
          <Button size="small" type="link">管理</Button>
        </Link>
      }
    >
      {plans.length === 0 ? (
        <Empty
          description={
            <Space direction="vertical" size={4}>
              <span>暂无运行中预案</span>
              <Link to="/plans">前往新建</Link>
            </Space>
          }
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      ) : (
        <List
          size="small"
          dataSource={plans}
          renderItem={(p) => (
            <List.Item>
              <List.Item.Meta
                title={
                  <Space>
                    <Link to="/plans">{p.name}</Link>
                    <Tag color={p.status === 'active' ? 'green' : 'orange'}>
                      {PLAN_STATUS_LABEL[p.status] ?? p.status}
                    </Tag>
                    {p.is_builtin && <Tag color="gold">内置</Tag>}
                  </Space>
                }
                description={p.description}
              />
            </List.Item>
          )}
        />
      )}
    </Card>
  );
}

// ── Plan Run Alerts (G1/G2 feedback) ─────────────────────────────────

const CYCLE_POSITION_LABEL: Record<string, string> = {
  extreme_low: '极度低估',
  low: '低估',
  mid: '中等',
  high: '高估',
  extreme_high: '极度高估',
};

function PlanRunAlerts({ plans }: { plans: CockpitResponse['plans'] }) {
  if (!plans || plans.length === 0) return null;

  // Build up to 1 alert per plan (priority: error > warning > info), then take first 3 to avoid noise
  const alerts: {
    type: 'error' | 'warning' | 'info';
    message: string;
    description?: string;
  }[] = [];

  for (const p of plans) {
    const s = p.last_run_summary;
    if (!s) continue;

    if (s.cycle_unavailable_skipped) {
      alerts.push({
        type: 'error',
        message: `Plan「${p.name}」跳过运行：周期数据缺失`,
        description:
          'Lixinger 同步失败或 CashflowGoal 未配置 current_index_pe_pct。请到数据管理页检查后手动触发 plan。',
      });
      continue;
    }

    if ((s.cycle_buy_blocked ?? 0) > 0) {
      alerts.push({
        type: 'warning',
        message: `Plan「${p.name}」：${s.cycle_buy_blocked} 个 BUY drafts 被周期阻断`,
        description: `当前周期 ${CYCLE_POSITION_LABEL[s.cycle_position ?? 'mid'] ?? s.cycle_position}，plan 阈值 cycle_buy_max=${p.cycle_buy_max ?? 'mid'}。到 Plan 编辑页可调阈值。`,
      });
      continue;
    }

    if ((s.filtered_midstream_non_leader ?? 0) > 0) {
      alerts.push({
        type: 'info',
        message: `Plan「${p.name}」：${s.filtered_midstream_non_leader} 股被中游过滤剔除`,
        description:
          'invest3 §13: 中游企业除非成本最低，否则剔除。到 StockDetail 标记成本领先者可保留。',
      });
    }
  }

  if (alerts.length === 0) return null;

  return (
    <div style={{ marginBottom: 'var(--sp-3)', display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
      {alerts.slice(0, 3).map((a, i) => (
        <Alert
          key={i}
          type={a.type}
          showIcon
          banner
          message={a.message}
          description={a.description}
        />
      ))}
    </div>
  );
}

// ── page ──────────────────────────────────────────────────────────────

/** Top-of-page banner for critical system alerts (Q15 B-min decision).
 * Renders when there are unresolved critical alerts (e.g. Lixinger token
 * expired, circuit open). Non-blocking — visual reminder only. Click → /data
 * for details and remediation. */
function SystemAlertBanner() {
  const q = useCriticalAlertsQuery();
  const alerts = q.data ?? [];
  if (alerts.length === 0) return null;
  const latest = alerts[0];
  const extra = alerts.length > 1 ? `（另 ${alerts.length - 1} 条）` : '';
  return (
    <Link to="/data" style={{ display: 'block', marginBottom: 'var(--sp-3)' }}>
      <Alert
        type="error"
        showIcon
        banner
        message={`⚠️ 数据可能过期或异常：${latest.message}${extra}`}
        description={
          <span>
            系统检测到 {alerts.length} 条 critical 警报。点击查看详情并修复。
            <strong> 修复前请审慎评估 draft 与告警的可信度。</strong>
          </span>
        }
      />
    </Link>
  );
}

export default function CockpitPage() {
  const cockpitQ = useCockpitQuery();
  const themeExposureQ = useThemeExposureQuery();
  const executeM = useExecuteDraftMutation();
  const cancelM = useCancelDraftMutation();

  const [goalEditorOpen, setGoalEditorOpen] = useState(false);
  const [disciplineTarget, setDisciplineTarget] = useState<{
    id: number;
    side: 'BUY' | 'SELL';
    code: string;
    tier: string | null;
    theme: string | null;
    hasPlan: boolean;
    suggestedQuantity: number | null;
  } | null>(null);

  const data = cockpitQ.data;

  const handleExecute = (id: number) => {
    const draft = data?.drafts.find((d) => d.id === id);
    if (!draft) return;
    const holding = data?.holdings.items.find((h) => h.stock_code === draft.code);
    const plan = data?.plans.find((p) => p.id === draft.plan_id);
    setDisciplineTarget({
      id,
      side: draft.side,
      code: draft.code,
      tier: holding?.stock_tier ?? null,
      theme: null,
      hasPlan: !!plan,
      suggestedQuantity: draft.suggested_quantity ?? null,
    });
  };

  const handleDisciplineConfirm = async (
    checklist: Record<string, boolean>,
    fill: { price: number; quantity: number },
  ) => {
    if (!disciplineTarget) return;
    await executeM.mutateAsync({
      id: disciplineTarget.id,
      payload: {
        discipline_checklist: checklist,
        buy_price: fill.price,
        quantity: fill.quantity,
      },
    });
    setDisciplineTarget(null);
  };

  const handleCancel = (id: number) => {
    Modal.confirm({
      title: '取消该订单草稿？',
      content: '取消后该档位可在下一次评估时重新触发。',
      okText: '取消草稿',
      cancelText: '保留',
      okButtonProps: { danger: true },
      onOk: () => cancelM.mutateAsync(id),
    });
  };

  if (cockpitQ.isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (cockpitQ.isError || !data) {
    return (
      <Alert
        type="error"
        message="无法加载 Cockpit"
        description={cockpitQ.error?.message ?? '请检查后端服务'}
        showIcon
      />
    );
  }

  return (
    <div>
      <PageHeader
        title="自动驾驶舱"
        enLabel="Cockpit"
        purpose="自动驾驶舱的 HUD：现金流目标进度、今日草稿、市场周期、主题偏离、再平衡建议、持仓审计一站式可读。"
        flow={[{ label: '主看板' }]}
        actions={
          <Text type="secondary" style={{ fontSize: 'var(--fs-xs)' }}>
            <span className="num">{data.as_of}</span> ·{' '}
            <a onClick={() => cockpitQ.refetch()}>
              {cockpitQ.isFetching ? '刷新中…' : '刷新'}
            </a>
          </Text>
        }
      />

      {data.errors.length > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 'var(--sp-3)' }}
          message="部分数据源不可用"
          description={data.errors.join('；')}
        />
      )}

      <SystemAlertBanner />

      <PlanRunAlerts plans={data.plans} />

      <GoalNavigator data={data.cashflow} onEdit={() => setGoalEditorOpen(true)} />
      <GoalEditor open={goalEditorOpen} onClose={() => setGoalEditorOpen(false)} />
      <DraftList
        drafts={data.drafts}
        onExecute={handleExecute}
        onCancel={handleCancel}
        executePending={executeM.isPending}
        cancelPending={cancelM.isPending}
      />

      <div className="cockpit-grid">
        <div className="cockpit-span-8">
          <CycleDashboardCard temperature={data.market_temperature} cycle={data.cycle} />
        </div>
        <div className="cockpit-span-16">
          {themeExposureQ.isLoading ? (
            <Card className="gojira-card" bordered={false} title="主题配置偏离" style={{ marginBottom: 0 }}>
              <Spin />
            </Card>
          ) : (
            <ThemeExposureCard data={themeExposureQ.data ?? null} />
          )}
        </div>

        <div className="cockpit-span-full">
          <SerenitySummaryCard summary={data.serenity_summary ?? null} />
        </div>

        <div className="cockpit-span-full">
          <PendingClaimVariablesBadge />
        </div>

        <div className="cockpit-span-full">
          <RebalancingSuggestionsCard suggestions={data.rebalance_suggestions ?? []} />
        </div>

        <div className="cockpit-span-full">
          <Card className="gojira-card" bordered={false} title="股息预测" style={{ marginBottom: 0 }} size="small">
            {data.dividend_projection && data.dividend_projection.next_12m_expected > 0 ? (
              <>
                <Row gutter={16}>
                  <Col span={8}>
                    <Statistic
                      title="未来12月预期"
                      value={data.dividend_projection.next_12m_expected}
                      precision={0}
                      prefix="¥"
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="目标"
                      value={data.dividend_projection.annual_passive_target ?? 0}
                      precision={0}
                      prefix="¥"
                      styles={{
                        content:
                          data.dividend_projection.dividend_gap && data.dividend_projection.dividend_gap > 0
                            ? { color: 'var(--red-600)' }
                            : { color: 'var(--green-600)' },
                      }}
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="覆盖率"
                      value={(data.dividend_projection.dividend_coverage ?? 0) * 100}
                      precision={1}
                      suffix="%"
                    />
                  </Col>
                </Row>
                {data.dividend_projection.by_holding.length > 0 && (
                  <div style={{ marginTop: 8 }}>
                    {data.dividend_projection.by_holding.map((h) => (
                      <Tag key={h.code} style={{ marginBottom: 4 }}>
                        {h.name} <span className="num">¥{h.expected_total.toFixed(0)}</span>
                        {h.expected_ex_month ? ` (${h.expected_ex_month}月)` : ''}
                      </Tag>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <Empty description="暂无股息预测数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </div>

        <div className="cockpit-span-full">
          {data.thesis_alerts && data.thesis_alerts.length > 0 ? (
            <Alert
              type="warning"
              showIcon
              message={`${data.thesis_alerts.length} 个论点变量越界`}
              description={data.thesis_alerts.map((a) => a.message).join('；')}
            />
          ) : (
            <Card className="gojira-card" bordered={false} style={{ marginBottom: 0 }}>
              <Empty description="论点变量均正常" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            </Card>
          )}
        </div>

        <div className="cockpit-span-12">
          <QuadrantPie data={data.quadrant} />
        </div>
        <div className="cockpit-span-12">
          <AlertsList alerts={data.alerts} />
        </div>

        <div className="cockpit-span-14">
          <HoldingsTable items={data.holdings.items} />
        </div>
        <div className="cockpit-span-10">
          <PlansList plans={data.plans} />
        </div>

        <div className="cockpit-span-full">
          <PendingCorpActionsCard />
        </div>
      </div>

      <DisciplineChecklistModal
        open={disciplineTarget !== null}
        side={disciplineTarget?.side ?? 'BUY'}
        stockCode={disciplineTarget?.code ?? ''}
        theme={disciplineTarget?.theme ?? null}
        tier={disciplineTarget?.tier ?? null}
        suggestedQuantity={disciplineTarget?.suggestedQuantity ?? null}
        autoChecks={{
          in_plan: disciplineTarget?.hasPlan ?? false,
          position_ok: true,
          is_production_asset: !!disciplineTarget?.tier,
          high_dyr_baseline: undefined,
        }}
        onConfirm={handleDisciplineConfirm}
        onCancel={() => setDisciplineTarget(null)}
      />
    </div>
  );
}


// ── Serenity Summary Card (Q7 D: Cockpit 辅助入口) ──────────────────────

function SerenitySummaryCard({ summary }: { summary: SerenityCockpitSummary | null }) {
  if (!summary) {
    return (
      <Card className="gojira-card" bordered={false} title="今日 serenity" style={{ marginBottom: 0 }}>
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            <span>
              还没有完成的 serenity 研究。<Link to="/research">前往研究方向</Link> 触发首次研究。
            </span>
          }
        />
      </Card>
    );
  }

  return (
    <Card
      className="gojira-card"
      bordered={false}
      title={
        <Space>
          <span>今日 serenity</span>
          <Link to={`/research/${summary.theme_id}`}>
            <Tag color="blue">{summary.theme_name}</Tag>
          </Link>
        </Space>
      }
      extra={
        <Link to={`/research/${summary.theme_id}`}>查看完整 →</Link>
      }
      style={{ marginBottom: 0 }}
    >
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <div>
          <Text type="secondary" style={{ fontSize: 12 }}>系统变化</Text>
          <div style={{ marginTop: 4 }}>{summary.system_change_excerpt}</div>
        </div>
        <Row gutter={16}>
          <Col span={8}>
            <Text type="secondary" style={{ fontSize: 12 }}>Token Input</Text>
            <div className="num">{summary.token_input.toLocaleString()}</div>
          </Col>
          <Col span={8}>
            <Text type="secondary" style={{ fontSize: 12 }}>Token Output</Text>
            <div className="num">{summary.token_output.toLocaleString()}</div>
          </Col>
          <Col span={8}>
            <Text type="secondary" style={{ fontSize: 12 }}>Web Search</Text>
            <div className="num">{summary.search_count}</div>
          </Col>
        </Row>
        <div>
          <Text type="secondary" style={{ fontSize: 12 }}>Top {summary.top_rankings.length} 公司</Text>
          <div style={{ marginTop: 8 }}>
            <Space direction="vertical" style={{ width: '100%' }}>
              {summary.top_rankings.map((r) => (
                <div key={r.rank} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Tag color="gold">#{r.rank}</Tag>
                  <Link to={`/stock/${r.stock_code}`}><code>{r.stock_code}</code></Link>
                  <span style={{ color: 'var(--stone-600)', fontSize: 13 }}>
                    {r.constrains_what}
                  </span>
                </div>
              ))}
            </Space>
          </div>
        </div>
      </Space>
    </Card>
  );
}
