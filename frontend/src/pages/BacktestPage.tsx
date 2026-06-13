import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  DatePicker,
  Divider,
  Form,
  Input,
  InputNumber,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PlayCircleOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { Dayjs } from 'dayjs';
import ReactECharts from 'echarts-for-react';

import echarts from '../lib/echarts';
import PageHeader from '../components/PageHeader';
import { useAntdStatic } from '../hooks/useAntdStatic';
import { listBacktests, submitBacktest } from '../api/client';
import type {
  BacktestConfig,
  BacktestRun,
  BacktestRule,
  TradeRecord,
} from '../api/types';

const { Text, Paragraph } = Typography;
const { RangePicker } = DatePicker;

const MONTHS = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12'];

interface ConfigFormValues {
  stock_codes: string;
  range: [Dayjs, Dayjs];
  initial_capital: number;
  slippage_bps: number;
  strategy_rules_text?: string;
}

function parseStockCodes(raw: string): string[] {
  return raw
    .split(/[,，\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function formatPercent(fraction: number | null | undefined, digits = 2): string {
  if (fraction == null || !Number.isFinite(fraction)) return '—';
  return `${(fraction * 100).toFixed(digits)}%`;
}

function formatCurrency(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `¥${value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`;
}

function MetricCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  tone?: 'positive' | 'negative' | 'neutral';
}) {
  const color =
    tone === 'positive'
      ? 'var(--green-600)'
      : tone === 'negative'
        ? 'var(--red-600)'
        : 'inherit';
  return (
    <Card size="small" style={{ minWidth: 150, textAlign: 'center' }}>
      <div style={{ fontSize: 12, color: 'var(--gray-500)' }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 600, marginTop: 4, color }}>{value}</div>
    </Card>
  );
}

interface MonthlyRow {
  year: string;
  [month: string]: string | number;
}

function MonthlyReturnsTable({ monthly }: { monthly: Record<string, number> }) {
  const rows: MonthlyRow[] = useMemo(() => {
    const byYear: Record<string, Record<string, number>> = {};
    for (const key of Object.keys(monthly).sort()) {
      const [y, m] = key.split('-');
      if (!y || !m) continue;
      if (!byYear[y]) byYear[y] = {};
      byYear[y][m] = monthly[key];
    }
    return Object.entries(byYear).map(([year, months]) => ({
      year,
      ...months,
    }));
  }, [monthly]);

  if (rows.length === 0) {
    return <Text type="secondary">无月度收益数据</Text>;
  }

  const columns: ColumnsType<MonthlyRow> = [
    {
      title: '年份',
      dataIndex: 'year',
      width: 80,
      fixed: 'left',
    },
    ...MONTHS.map((m) => ({
      title: m,
      dataIndex: m,
      width: 80,
      render: (v: number | undefined) =>
        v !== undefined && v !== null ? (
          <span style={{ color: v >= 0 ? 'var(--green-600)' : 'var(--red-600)' }}>
            {(v * 100).toFixed(1)}%
          </span>
        ) : (
          <span style={{ color: 'var(--gray-300)' }}>—</span>
        ),
    })),
  ];

  return (
    <Table<MonthlyRow>
      size="small"
      pagination={false}
      dataSource={rows}
      rowKey="year"
      columns={columns}
      scroll={{ x: 1100 }}
    />
  );
}

export default function BacktestPage() {
  const { message } = useAntdStatic();
  const [form] = Form.useForm<ConfigFormValues>();
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<BacktestRun | null>(null);
  const [history, setHistory] = useState<BacktestRun[]>([]);
  const [rulesError, setRulesError] = useState<string | null>(null);

  const fetchHistory = useCallback(async () => {
    try {
      const runs = await listBacktests();
      setHistory(runs);
    } catch {
      // silent — history is a secondary view
    }
  }, []);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const handleSubmit = async () => {
    let values: ConfigFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return; // antd validation surfaces inline errors
    }

    let rules: BacktestRule[] = [];
    const rulesText = (values.strategy_rules_text || '').trim();
    if (rulesText) {
      try {
        const parsed = JSON.parse(rulesText);
        if (!Array.isArray(parsed)) {
          throw new Error('策略规则必须是 JSON 数组');
        }
        rules = parsed as BacktestRule[];
        setRulesError(null);
      } catch (e) {
        setRulesError(e instanceof Error ? e.message : 'JSON 解析失败');
        message.error('策略规则 JSON 格式错误');
        return;
      }
    } else {
      setRulesError(null);
    }

    const codes = parseStockCodes(values.stock_codes);
    if (codes.length === 0) {
      message.error('请至少填写一个股票代码');
      return;
    }

    const config: BacktestConfig = {
      stock_codes: codes,
      start_date: values.range[0].format('YYYY-MM-DD'),
      end_date: values.range[1].format('YYYY-MM-DD'),
      initial_capital: values.initial_capital ?? 1_000_000,
      slippage_bps: values.slippage_bps ?? 10,
      strategy_rules: rules,
    };

    setSubmitting(true);
    try {
      const run = await submitBacktest(config);
      setResult(run);
      if (run.status === 'completed') {
        message.success(`回测完成 #${run.id}`);
      } else if (run.status === 'failed') {
        message.warning(`回测失败 #${run.id} — 请查看错误信息`);
      }
      fetchHistory();
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e instanceof Error ? e.message : '提交失败');
      message.error(detail);
    } finally {
      setSubmitting(false);
    }
  };

  // ── Equity curve ECharts option ───────────────────────────────────────
  const equityOption = useMemo(() => {
    const curve = result?.result_json?.equity_curve;
    if (!curve || curve.length === 0) return null;
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis' as const },
      grid: { left: '6%', right: '4%', top: '10%', bottom: '15%' },
      xAxis: {
        type: 'category' as const,
        data: curve.map((p) => p.date),
        axisLabel: { fontSize: 10, color: 'var(--gray-500)' },
      },
      yAxis: {
        type: 'value' as const,
        name: '¥',
        axisLabel: {
          formatter: (v: number) =>
            v >= 10_000 ? `${(v / 10_000).toFixed(0)}万` : String(v),
        },
      },
      dataZoom: [
        { type: 'inside' as const, start: 0, end: 100 },
        { type: 'slider' as const, start: 0, end: 100, height: 18, bottom: 8 },
      ],
      series: [
        {
          name: '组合净值',
          type: 'line' as const,
          data: curve.map((p) => p.value),
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 2, color: '#4F6D93' },
          areaStyle: { opacity: 0.08 },
        },
      ],
    };
  }, [result]);

  const metrics = result?.result_json?.metrics;

  const tradeColumns: ColumnsType<TradeRecord> = [
    {
      title: '日期',
      dataIndex: 'date',
      width: 110,
      render: (v?: string | null) => v ?? '—',
    },
    {
      title: '方向',
      dataIndex: 'side',
      width: 90,
      render: (s: TradeRecord['side']) => {
        const color = s === 'BUY' ? 'success' : s === 'SELL' ? 'error' : 'processing';
        return <Tag color={color}>{s}</Tag>;
      },
    },
    { title: '代码', dataIndex: 'code', width: 90 },
    {
      title: '数量',
      dataIndex: 'qty',
      width: 90,
      align: 'right' as const,
      render: (v: number) => v.toLocaleString('zh-CN'),
    },
    {
      title: '价格',
      dataIndex: 'price',
      width: 90,
      align: 'right' as const,
      render: (v: number) => `¥${v.toFixed(2)}`,
    },
    {
      title: '总额',
      dataIndex: 'total',
      width: 130,
      align: 'right' as const,
      render: (v: number) => formatCurrency(Math.abs(v)),
    },
    {
      title: '已实现盈亏',
      dataIndex: 'realized_pnl',
      width: 130,
      align: 'right' as const,
      render: (v?: number) =>
        v !== undefined && v !== null ? (
          <span style={{ color: v >= 0 ? 'var(--green-600)' : 'var(--red-600)' }}>
            {formatCurrency(v)}
          </span>
        ) : (
          '—'
        ),
    },
  ];

  const historyColumns: ColumnsType<BacktestRun> = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (s: BacktestRun['status']) => {
        const color =
          s === 'completed' ? 'success' : s === 'failed' ? 'error' : 'processing';
        return <Tag color={color}>{s}</Tag>;
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 160,
      render: (s: string) => dayjs(s).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '股票',
      width: 220,
      render: (_: unknown, r: BacktestRun) =>
        r.config_json.stock_codes?.join(', ') || '—',
    },
    {
      title: '时间范围',
      width: 220,
      render: (_: unknown, r: BacktestRun) =>
        `${r.config_json.start_date} ~ ${r.config_json.end_date}`,
    },
    {
      title: '总收益',
      width: 110,
      render: (_: unknown, r: BacktestRun) => {
        const m = r.result_json?.metrics;
        if (!m) return '—';
        const tone = m.total_return >= 0 ? 'positive' : 'negative';
        return (
          <span
            style={{
              color:
                tone === 'positive' ? 'var(--green-600)' : 'var(--red-600)',
            }}
          >
            {formatPercent(m.total_return)}
          </span>
        );
      },
    },
  ];

  return (
    <div>
      <PageHeader
        title="回测"
        enLabel="Backtest"
        icon={<PlayCircleOutlined />}
        description="基于历史数据回放策略规则，计算 CAGR / Sharpe / 最大回撤 / 胜率等指标"
      />

      {/* ── 配置卡片 ─────────────────────────────────────────────────── */}
      <Card title="回测配置" style={{ marginBottom: 16 }}>
        <Form<ConfigFormValues>
          form={form}
          layout="vertical"
          initialValues={{
            initial_capital: 1_000_000,
            slippage_bps: 10,
          }}
        >
          <Space wrap size="large" align="end">
            <Form.Item
              name="stock_codes"
              label="股票代码"
              rules={[{ required: true, message: '请输入股票代码' }]}
              extra="多个代码用逗号或空格分隔，例如 600519,000001"
            >
              <Input placeholder="600519, 000001" style={{ width: 240 }} />
            </Form.Item>

            <Form.Item
              name="range"
              label="时间范围"
              rules={[{ required: true, message: '请选择时间范围' }]}
            >
              <RangePicker style={{ width: 260 }} />
            </Form.Item>

            <Form.Item name="initial_capital" label="初始资金 (¥)">
              <InputNumber min={1_000} step={100_000} style={{ width: 160 }} />
            </Form.Item>

            <Form.Item name="slippage_bps" label="滑点 (bps)" extra="10 = 0.1%">
              <InputNumber min={0} max={200} style={{ width: 120 }} />
            </Form.Item>
          </Space>

          <Divider style={{ margin: '8px 0 16px' }} />

          <Form.Item
            name="strategy_rules_text"
            label="策略规则 (JSON, 可选)"
            validateStatus={rulesError ? 'error' : undefined}
            help={
              rulesError ?? (
                <span>
                  示例：
                  <code>
                    {'[{"metric":"pe_ttm","operator":"<","threshold":25,"action":"BUY","target_pct":0.5}]'}
                  </code>
                </span>
              )
            }
          >
            <Input.TextArea
              rows={4}
              placeholder='[{"metric":"pe_ttm","operator":"<","threshold":25,"action":"BUY","target_pct":0.5}]'
              style={{ fontFamily: 'monospace', fontSize: 12 }}
            />
          </Form.Item>

          <Button
            type="primary"
            size="large"
            icon={<PlayCircleOutlined />}
            onClick={handleSubmit}
            loading={submitting}
          >
            运行回测
          </Button>
        </Form>
      </Card>

      {/* ── 结果区 ──────────────────────────────────────────────────── */}
      {result?.status === 'completed' && result.result_json && metrics && (
        <>
          <Card title="核心指标" style={{ marginBottom: 16 }}>
            <Space size="middle" wrap>
              <MetricCard
                label="总收益"
                value={formatPercent(metrics.total_return)}
                tone={metrics.total_return >= 0 ? 'positive' : 'negative'}
              />
              <MetricCard
                label="CAGR"
                value={formatPercent(metrics.cagr)}
                tone={metrics.cagr >= 0 ? 'positive' : 'negative'}
              />
              <MetricCard label="Sharpe" value={metrics.sharpe.toFixed(2)} />
              <MetricCard
                label="最大回撤"
                value={formatPercent(metrics.max_drawdown)}
                tone="negative"
              />
              <MetricCard
                label="胜率"
                value={`${(metrics.win_rate * 100).toFixed(1)}%`}
              />
              <MetricCard label="交易次数" value={metrics.trade_count} />
              {metrics.alpha !== null && metrics.alpha !== undefined && (
                <MetricCard
                  label="Alpha (vs 基准)"
                  value={formatPercent(metrics.alpha)}
                  tone={metrics.alpha >= 0 ? 'positive' : 'negative'}
                />
              )}
            </Space>
            <Divider style={{ margin: '16px 0 12px' }} />
            <Space size="large" wrap>
              <Text type="secondary">
                最终现金: <strong>{formatCurrency(result.result_json.final_cash)}</strong>
              </Text>
              <Text type="secondary">
                持仓数量:{' '}
                <strong>
                  {Object.keys(result.result_json.final_positions).length}
                </strong>{' '}
                只
              </Text>
              <Text type="secondary">
                基准收益:{' '}
                <strong>{formatPercent(metrics.benchmark_return)}</strong>
              </Text>
            </Space>
          </Card>

          {equityOption && (
            <Card title="净值曲线" style={{ marginBottom: 16 }}>
              <ReactECharts
                echarts={echarts}
                option={equityOption}
                style={{ height: 400 }}
                notMerge
              />
            </Card>
          )}

          <Card title="月度收益" style={{ marginBottom: 16 }}>
            <MonthlyReturnsTable monthly={result.result_json.monthly_returns} />
          </Card>

          <Card title="信号明细" style={{ marginBottom: 16 }}>
            <Table<TradeRecord>
              size="small"
              dataSource={result.result_json.trades_log}
              rowKey={(_, idx) => String(idx)}
              columns={tradeColumns}
              pagination={{ pageSize: 20, showSizeChanger: true }}
              scroll={{ x: 760 }}
            />
          </Card>
        </>
      )}

      {result?.status === 'failed' && (
        <Card title="回测失败" style={{ marginBottom: 16 }}>
          <Paragraph type="danger" style={{ marginBottom: 0 }}>
            {result.error_message || '未知错误'}
          </Paragraph>
        </Card>
      )}

      {/* ── 历史回测 ────────────────────────────────────────────────── */}
      {history.length > 0 && (
        <Card title="历史回测">
          <Table<BacktestRun>
            size="small"
            dataSource={history}
            rowKey="id"
            columns={historyColumns}
            pagination={{ pageSize: 10, showSizeChanger: false }}
            onRow={(r) => ({
              onClick: () => setResult(r),
              style: { cursor: 'pointer' },
            })}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            点击行可重新展示该回测结果
          </Text>
        </Card>
      )}
    </div>
  );
}
