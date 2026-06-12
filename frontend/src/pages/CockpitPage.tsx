/**
 * Cockpit — autopilot main dashboard.
 *
 * Single-screen "HUD" for the personal-investing autopilot. Reads
 * `GET /api/cockpit` (one aggregator) and renders:
 *   ① Cashflow goal progress / weighted DYR / annual passive cashflow
 *   ② Today's BUY/SELL drafts (with one-click execute / cancel)
 *   ③ Four-quadrant breakdown pie
 *   ④ Holdings compact table
 *   ⑤ Unacked alerts list
 *   ⑥ Active plans list
 *
 * Per the redesign: the human's only inputs are predefined plans, then
 * placing real orders + backfilling fills. Everything else is read-only here.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
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

import echarts from '../lib/echarts';
import { useAntdStatic } from '../hooks/useAntdStatic';
import DisciplineChecklistModal from '../components/DisciplineChecklistModal';
import DraftAvailableCell from '../components/DraftAvailableCell';
import PageHeader from '../components/PageHeader';
import {
  cancelDraft,
  executeDraft,
  fetchCashflowGoal,
  fetchCockpit,
  getThemeExposure,
  updateCashflowGoal,
} from '../api/client';
import type { CashflowGoalUpdate } from '../api/types';
import type {
  CockpitDraft,
  CockpitHoldingItem,
  CockpitQuadrant,
  CockpitResponse,
  ThemeExposure,
  RebalanceSuggestion,
} from '../api/types';

const { Title, Text } = Typography;

// ── helpers ───────────────────────────────────────────────────────────

function formatCurrency(value: number | null | undefined, currency = 'CNY'): string {
  if (value == null) return '—';
  const symbol = currency === 'CNY' ? '¥' : currency;
  return `${symbol}${new Intl.NumberFormat('en-US', {
    maximumFractionDigits: 0,
  }).format(value)}`;
}

function formatPct(decimal: number | null | undefined, fractionDigits = 2): string {
  if (decimal == null) return '—';
  return `${(decimal * 100).toFixed(fractionDigits)}%`;
}

function progressColor(progress: number): string {
  if (progress >= 1) return '#52c41a';
  if (progress >= 0.7) return '#4F6D93';
  if (progress >= 0.3) return '#faad14';
  return '#ff4d4f';
}

const QUADRANT_LABEL: Record<string, string> = {
  procyclical: '顺周期',
  countercyclical: '逆周期',
  distressed_reversal: '困境反转',
  financial: '金融',
  unlabeled: '未分类',
};

const DRAFT_SIDE_LABEL: Record<string, string> = {
  BUY: '买入',
  SELL: '卖出',
};

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

// ── sub-components ────────────────────────────────────────────────────

function CycleDashboardCard({
  temperature,
  cycle,
}: {
  temperature: number | null | undefined;
  cycle: import('../api/types').CycleAssessment | undefined;
}) {
  // Market temperature visual
  let tempColor = '#8C8C8C';
  let tempLabel = '未知';
  let tempValue = '—';

  if (temperature != null) {
    tempValue = temperature.toFixed(0);
    if (temperature <= 30) {
      tempColor = '#4F6D93';
      tempLabel = '冷';
    } else if (temperature <= 70) {
      tempColor = '#A8A29E';
      tempLabel = '温';
    } else {
      tempColor = '#DC2626';
      tempLabel = '热';
    }
  }

  // Cycle position label
  const cycleLabels: Record<string, { label: string; color: string }> = {
    extreme_low: { label: '极度低估', color: '#059669' },
    low: { label: '低估', color: '#10b981' },
    mid: { label: '中等', color: '#6b7280' },
    high: { label: '偏高', color: '#f59e0b' },
    extreme_high: { label: '极度高估', color: '#dc2626' },
  };

  const pos = cycle?.cycle_position
    ? cycleLabels[cycle.cycle_position] ?? { label: cycle.cycle_position, color: '#6b7280' }
    : null;

  return (
    <Card title="市场周期" style={{ marginBottom: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
        {/* Temperature circle */}
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
            <div style={{ fontSize: 22, lineHeight: 1 }}>{tempValue}</div>
            <div style={{ fontSize: 11 }}>{tempLabel}</div>
          </div>
          <Text type="secondary" style={{ fontSize: 11, marginTop: 4, display: 'block' }}>
            PE 分位
          </Text>
        </div>

        {/* Cycle position */}
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
                建议仓位 {((cycle.position_range[0]) * 100).toFixed(0)}%–{((cycle.position_range[1]) * 100).toFixed(0)}%
              </Text>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

function ThemeExposureCard({ data }: { data: ThemeExposure | null }) {
  if (!data || data.targets.length === 0) {
    return (
      <Card title="主题配置" style={{ marginBottom: 0 }}>
        <Empty
          description="暂无主题配置"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </Card>
    );
  }

  const columns: ColumnsType<ThemeExposure['targets'][number]> = [
    {
      title: '主题',
      dataIndex: 'theme',
      width: 120,
    },
    {
      title: '目标%',
      dataIndex: 'target_pct',
      width: 80,
      align: 'right',
      render: (v: number) => `${(v * 100).toFixed(1)}%`,
    },
    {
      title: '实际%',
      dataIndex: 'actual_pct',
      width: 80,
      align: 'right',
      render: (v: number) => `${(v * 100).toFixed(1)}%`,
    },
    {
      title: '偏离%',
      dataIndex: 'drift_pct',
      width: 80,
      align: 'right',
      render: (v: number) => {
        const pct = (v * 100).toFixed(1);
        const absV = Math.abs(v);
        let color = '#52c41a';
        if (absV > 0.05) color = '#faad14';
        if (absV > 0.1) color = '#ff4d4f';
        return <span style={{ color }}>{pct}%</span>;
      },
    },
    {
      title: '状态',
      dataIndex: 'warning',
      width: 80,
      render: (warning: string | null) =>
        warning ? (
          <Tag color="orange" style={{ fontSize: 11 }}>
            {warning}
          </Tag>
        ) : (
          <Tag color="green" style={{ fontSize: 11 }}>
            正常
          </Tag>
        ),
    },
  ];

  return (
    <Card
      title="主题配置偏离"
      style={{ marginBottom: 0 }}
      extra={
        data.warnings.length > 0 && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {data.warnings.length} 条警告
          </Text>
        )
      }
    >
      <Table
        dataSource={data.targets}
        columns={columns}
        rowKey="theme"
        size="small"
        pagination={false}
      />
    </Card>
  );
}

function RebalancingSuggestionsCard({
  suggestions,
}: {
  suggestions: RebalanceSuggestion[];
}) {
  if (!suggestions || suggestions.length === 0) {
    return (
      <Card title="再平衡建议" style={{ marginBottom: 0 }}>
        <Empty
          description="暂无再平衡建议"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
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
        if (r.level === 'quadrant' && r.quadrant) {
          return <Tag>{r.quadrant}</Tag>;
        }
        if (r.level === 'theme' && r.theme) {
          return <Tag>{r.theme}</Tag>;
        }
        return '—';
      },
    },
    {
      title: '当前%',
      dataIndex: 'current_pct',
      width: 80,
      align: 'right',
      render: (v: number) => `${(v * 100).toFixed(1)}%`,
    },
    {
      title: '目标%',
      dataIndex: 'target_pct',
      width: 80,
      align: 'right',
      render: (v: number) => `${(v * 100).toFixed(1)}%`,
    },
    {
      title: '偏离%',
      dataIndex: 'drift_pct',
      width: 80,
      align: 'right',
      render: (v: number) => {
        const pct = (v * 100).toFixed(1);
        const color = Math.abs(v) > 0.05 ? '#ff4d4f' : '#faad14';
        return <span style={{ color }}>{pct}%</span>;
      },
    },
    {
      title: '建议操作',
      dataIndex: 'action',
      width: 120,
      ellipsis: true,
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      width: 80,
      render: (priority: string) => {
        const colorMap: Record<string, string> = {
          high: 'red',
          medium: 'orange',
          low: 'green',
        };
        return (
          <Tag color={colorMap[priority] || 'default'} style={{ fontSize: 11 }}>
            {priority}
          </Tag>
        );
      },
    },
  ];

  return (
    <Card
      title={`再平衡建议 (${suggestions.length})`}
      style={{ marginBottom: 0 }}
    >
      <Table
        dataSource={suggestions}
        columns={columns}
        rowKey={(r) =>
          `${r.level}-${r.code || r.quadrant || r.theme || ''}-${r.current_pct}`
        }
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
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { message } = useAntdStatic();
  const [form] = Form.useForm<GoalFormValues>();
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    fetchCashflowGoal()
      .then((goal) => {
        if (cancelled) return;
        form.setFieldsValue({
          annual_expense: goal.annual_expense,
          goal_multiple: goal.goal_multiple,
          currency: goal.currency,
          notes: goal.notes ?? '',
          cash_reserve: goal.cash_reserve ?? 0,
        });
      })
      .catch((e) => {
        if (!cancelled)
          message.error(
            `读取目标失败：${e instanceof Error ? e.message : String(e)}`,
          );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, form]);

  const handleOk = async () => {
    let values: GoalFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    setSubmitting(true);
    try {
      const payload: CashflowGoalUpdate = {
        annual_expense: values.annual_expense,
        goal_multiple: values.goal_multiple,
        currency: values.currency,
        notes: values.notes || null,
        cash_reserve: values.cash_reserve,
      };
      await updateCashflowGoal(payload);
      message.success('目标已更新');
      onSaved();
      onClose();
    } catch (e) {
      const detail =
        (e as { response?: { data?: { detail?: unknown } } })?.response?.data
          ?.detail ?? String(e);
      message.error(
        typeof detail === 'string' ? detail : JSON.stringify(detail),
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      title="设定现金流目标"
      onCancel={onClose}
      onOk={handleOk}
      okText="保存"
      cancelText="取消"
      confirmLoading={submitting}
      destroyOnHidden
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 24 }}>
          <Spin />
        </div>
      ) : (
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            annual_expense: 0,
            goal_multiple: 15,
            currency: 'CNY',
          }}
        >
          <Form.Item
            label="年度开销"
            name="annual_expense"
            rules={[{ required: true, type: 'number', min: 0 }]}
            extra="日常生活年支出基线（不含投资本金）"
          >
            <InputNumber
              style={{ width: '100%' }}
              min={0}
              step={10000}
              addonAfter="元"
            />
          </Form.Item>
          <Form.Item
            label="目标倍数"
            name="goal_multiple"
            rules={[{ required: true, type: 'number', min: 0.01 }]}
            extra="原文建议 10–20×；默认 15×"
          >
            <InputNumber
              style={{ width: '100%' }}
              min={1}
              max={50}
              step={1}
              addonAfter="×"
            />
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
            现金流目标进度（{data.goal_multiple}× 年开销）
          </Text>
          <Title level={2} style={{ margin: '4px 0' }}>
            {data.goal_progress != null
              ? `${(progress * 100).toFixed(1)}%`
              : '尚未设定目标'}
          </Title>
          <Progress
            percent={progressPct}
            strokeColor={progressColor(progress)}
            showInfo={false}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            {formatCurrency(data.annual_passive_cashflow, data.currency)} /{' '}
            {formatCurrency(data.target_annual_cashflow, data.currency)}
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
                    ? '#52c41a'
                    : '#cf1322',
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
}: {
  drafts: CockpitDraft[];
  onExecute: (id: number) => void;
  onCancel: (id: number) => void;
}) {
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
      width: 110,
      render: (code: string) => <Link to={`/stock/${code}`}>{code}</Link>,
    },
    {
      title: '比例',
      width: 100,
      render: (_: unknown, r: CockpitDraft) =>
        r.side === 'BUY'
          ? `+组合 ${formatPct(r.add_pct, 1)}`
          : `−仓位 ${formatPct(r.reduce_pct_of_position, 0)}`,
    },
    {
      title: '触发原因',
      dataIndex: 'reason',
      ellipsis: true,
    },
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
          {r.source === 'rebalance' && (
            <Tag color="orange">系统</Tag>
          )}
        </Space>
      ),
    },
    {
      title: '操作',
      width: 170,
      render: (_: unknown, r: CockpitDraft) => (
        <Space size={4}>
          <Button size="small" type="primary" onClick={() => onExecute(r.id)}>
            标记已成交
          </Button>
          <Button size="small" danger onClick={() => onCancel(r.id)}>
            取消
          </Button>
        </Space>
      ),
    },
  ];
  return (
    <Card
      title={`今日订单草稿 (${drafts.length})`}
      style={{ marginBottom: 16 }}
      extra={
        drafts.length > 0 && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            人工去券商下单，回填后自动登记到持仓
          </Text>
        )
      }
    >
      {drafts.length === 0 ? (
        <Empty
          description="今日无草稿"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      ) : (
        <Table
          dataSource={drafts}
          columns={columns}
          rowKey="id"
          size="small"
          pagination={false}
        />
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
            itemStyle: {
              color: QUADRANT_COLOR[d.quadrant] || '#A8A29E',
            },
          })),
        },
      ],
    }),
    [data],
  );

  return (
    <Card title="四象限分布">
      {data.length === 0 ? (
        <Empty
          description="暂无可分配持仓"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      ) : (
        <ReactECharts echarts={echarts} option={option} style={{ height: 280 }} />
      )}
    </Card>
  );
}

function AlertsList({
  alerts,
}: {
  alerts: CockpitResponse['alerts'];
}) {
  return (
    <Card title={`未确认告警 (${alerts.unacked_count})`}>
      {alerts.items.length === 0 ? (
        <Empty
          description="一切正常"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
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
                    {ev.stock_code && (
                      <Link to={`/stock/${ev.stock_code}`}>
                        {ev.stock_code}
                      </Link>
                    )}
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
          <Tag color={v === 'core' ? '#B8860B' : '#6A5ACD'} style={{ fontSize: 11 }}>
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
      render: (v: number | undefined) => (v != null ? v.toFixed(1) : '—'),
    },
    {
      title: '市值',
      dataIndex: 'current_value',
      align: 'right',
      render: (v: number | null) => formatCurrency(v),
    },
  ];
  return (
    <Card title={`持仓 (${items.length})`}>
      <Table
        dataSource={items}
        columns={columns}
        rowKey="id"
        size="small"
        pagination={false}
      />
    </Card>
  );
}

function PlansList({ plans }: { plans: CockpitResponse['plans'] }) {
  return (
    <Card
      title={`运行中预案 (${plans.length})`}
      extra={
        <Link to="/plans">
          <Button size="small" type="link">
            管理
          </Button>
        </Link>
      }
    >
      {plans.length === 0 ? (
        <Empty
          description={
            <Space orientation="vertical" size={4}>
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

// ── page ──────────────────────────────────────────────────────────────

export default function CockpitPage() {
  const { message } = useAntdStatic();
  const [data, setData] = useState<CockpitResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [goalEditorOpen, setGoalEditorOpen] = useState(false);
  const [themeExposure, setThemeExposure] = useState<ThemeExposure | null>(null);
  const [themeExposureLoading, setThemeExposureLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const payload = await fetchCockpit();
      setData(payload);
      setError(null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshThemeExposure = useCallback(async () => {
    try {
      setThemeExposureLoading(true);
      const payload = await getThemeExposure();
      setThemeExposure(payload);
    } catch (e) {
      console.error('Failed to load theme exposure:', e);
    } finally {
      setThemeExposureLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    void refreshThemeExposure();
  }, [refresh, refreshThemeExposure]);

  const [disciplineTarget, setDisciplineTarget] = useState<{
    id: number;
    side: 'BUY' | 'SELL';
    code: string;
    tier: string | null;
    dyr: number | null;
    theme: string | null;
    hasPlan: boolean;
  } | null>(null);

  const handleExecute = useCallback(
    (id: number) => {
      const draft = data?.drafts.find((d) => d.id === id);
      if (!draft) return;
      const holding = data?.holdings.items.find((h) => h.stock_code === draft.code);
      const plan = data?.plans.find((p) => p.id === draft.plan_id);
      setDisciplineTarget({
        id,
        side: draft.side,
        code: draft.code,
        tier: holding?.stock_tier ?? null,
        dyr: null,
        theme: null,
        hasPlan: !!plan,
      });
    },
    [data],
  );

  const handleDisciplineConfirm = useCallback(
    async (checklist: Record<string, boolean>) => {
      if (!disciplineTarget) return;
      try {
        await executeDraft(disciplineTarget.id, checklist);
        message.success('已登记成交');
        setDisciplineTarget(null);
        await refresh();
      } catch (e) {
        const m = e instanceof Error ? e.message : String(e);
        message.error(`登记失败：${m}`);
      }
    },
    [disciplineTarget, refresh],
  );

  const handleCancel = useCallback(
    (id: number) => {
      Modal.confirm({
        title: '取消该订单草稿？',
        content: '取消后该档位可在下一次评估时重新触发。',
        okText: '取消草稿',
        cancelText: '保留',
        okButtonProps: { danger: true },
        onOk: async () => {
          try {
            await cancelDraft(id);
            message.success('已取消');
            await refresh();
          } catch (e) {
            const m = e instanceof Error ? e.message : String(e);
            message.error(`取消失败：${m}`);
          }
        },
      });
    },
    [refresh],
  );

  if (loading && !data) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!data) {
    return (
      <Alert
        type="error"
        message="无法加载 Cockpit"
        description={error || '请检查后端服务'}
        showIcon
      />
    );
  }

  return (
    <div>
      <PageHeader
        title="自动驾驶舱"
        enLabel="Cockpit"
        extra={
          <Text type="secondary" style={{ fontSize: 12 }}>
            {data.as_of} · <a onClick={() => void refresh()}>刷新</a>
          </Text>
        }
      />

      {data.errors.length > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 0 }}
          message="部分数据源不可用"
          description={data.errors.join('；')}
        />
      )}

      <GoalNavigator
        data={data.cashflow}
        onEdit={() => setGoalEditorOpen(true)}
      />
      <GoalEditor
        open={goalEditorOpen}
        onClose={() => setGoalEditorOpen(false)}
        onSaved={() => void refresh()}
      />
      <DraftList
        drafts={data.drafts}
        onExecute={handleExecute}
        onCancel={handleCancel}
      />

      <div className="cockpit-grid">
        <div className="cockpit-span-8">
          <CycleDashboardCard temperature={data.market_temperature} cycle={data.cycle} />
        </div>
        <div className="cockpit-span-16">
          {themeExposureLoading ? (
            <Card title="主题配置偏离" style={{ marginBottom: 0 }}>
              <Spin />
            </Card>
          ) : (
            <ThemeExposureCard data={themeExposure} />
          )}
        </div>

        <div className="cockpit-span-full">
          <RebalancingSuggestionsCard suggestions={data.rebalance_suggestions ?? []} />
        </div>

        <div className="cockpit-span-full">
          <Card title="股息预测" style={{ marginBottom: 0 }} size="small">
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
                      styles={{ content: data.dividend_projection.dividend_gap && data.dividend_projection.dividend_gap > 0
                        ? { color: '#cf1322' } : { color: '#3f8600' } }}
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
                    {data.dividend_projection.by_holding.map(h => (
                      <Tag key={h.code} style={{ marginBottom: 4 }}>
                        {h.name} ¥{h.expected_total.toFixed(0)}
                        {h.expected_ex_month ? ` (${h.expected_ex_month}月)` : ''}
                      </Tag>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <Empty
                description="暂无股息预测数据"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            )}
          </Card>
        </div>

        <div className="cockpit-span-full">
          {data.thesis_alerts && data.thesis_alerts.length > 0 ? (
            <Alert
              type="warning"
              showIcon
              message={`${data.thesis_alerts.length} 个论点变量越界`}
              description={data.thesis_alerts.map(a => a.message).join('；')}
            />
          ) : (
            <Card style={{ marginBottom: 0 }}>
              <Empty
                description="论点变量均正常"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
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
      </div>

      <DisciplineChecklistModal
        open={disciplineTarget !== null}
        side={disciplineTarget?.side ?? 'BUY'}
        stockCode={disciplineTarget?.code ?? ''}
        theme={disciplineTarget?.theme ?? null}
        tier={disciplineTarget?.tier ?? null}
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
