import { useMemo, useState } from 'react';
import {
  Button,
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

import echarts from '../../lib/echarts';
import { PageHeader, PageSection, StatCard } from '../../components/primitives';
import QueryBoundary from '../../components/QueryBoundary';
import { useAntdStatic } from '../../hooks/useAntdStatic';
import { useBacktestHistoryQuery } from './useBacktestQueries';
import { useSubmitBacktestMutation } from './useBacktestMutations';
import type {
  BacktestConfig,
  BacktestRun,
  BacktestRule,
  TradeRecord,
} from '../../api/types';

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
    { title: '年份', dataIndex: 'year', width: 80, fixed: 'left' },
    ...MONTHS.map((m) => ({
      title: m,
      dataIndex: m,
      width: 80,
      render: (v: number | undefined) =>
        v !== undefined && v !== null ? (
          <span
            className="num"
            style={{ color: v >= 0 ? 'var(--green-600)' : 'var(--red-600)' }}
          >
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
  const [result, setResult] = useState<BacktestRun | null>(null);
  const [rulesError, setRulesError] = useState<string | null>(null);

  const historyQ = useBacktestHistoryQuery(20);
  const submitM = useSubmitBacktestMutation();

  const history = historyQ.data ?? [];

  const handleSubmit = async () => {
    let values: ConfigFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
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

    try {
      const run = await submitM.mutateAsync(config);
      setResult(run);
    } catch {
      // toast handled by useToastMutation
    }
  };

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
      render: (v?: string | null) =>
        v ? <span className="num">{v}</span> : '—',
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
      render: (v: number) => <span className="num">{v.toLocaleString('zh-CN')}</span>,
    },
    {
      title: '价格',
      dataIndex: 'price',
      width: 90,
      align: 'right' as const,
      render: (v: number) => <span className="num">¥{v.toFixed(2)}</span>,
    },
    {
      title: '总额',
      dataIndex: 'total',
      width: 130,
      align: 'right' as const,
      render: (v: number) => <span className="num">{formatCurrency(Math.abs(v))}</span>,
    },
    {
      title: '已实现盈亏',
      dataIndex: 'realized_pnl',
      width: 130,
      align: 'right' as const,
      render: (v?: number) =>
        v !== undefined && v !== null ? (
          <span
            className="num"
            style={{ color: v >= 0 ? 'var(--green-600)' : 'var(--red-600)' }}
          >
            {formatCurrency(v)}
          </span>
        ) : (
          '—'
        ),
    },
  ];

  const historyColumns: ColumnsType<BacktestRun> = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 60,
      render: (v: number) => <span className="num">{v}</span>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (s: BacktestRun['status']) => {
        const color = s === 'completed' ? 'success' : s === 'failed' ? 'error' : 'processing';
        return <Tag color={color}>{s}</Tag>;
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 160,
      render: (s: string) => (
        <span className="num" style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}>
          {dayjs(s).format('YYYY-MM-DD HH:mm:ss')}
        </span>
      ),
    },
    {
      title: '股票',
      width: 220,
      render: (_: unknown, r: BacktestRun) => r.config_json.stock_codes?.join(', ') || '—',
    },
    {
      title: '时间范围',
      width: 220,
      render: (_: unknown, r: BacktestRun) => (
        <span className="num">
          {r.config_json.start_date} ~ {r.config_json.end_date}
        </span>
      ),
    },
    {
      title: '总收益',
      width: 110,
      render: (_: unknown, r: BacktestRun) => {
        const m = r.result_json?.metrics;
        if (!m) return '—';
        return (
          <span
            className="num"
            style={{ color: m.total_return >= 0 ? 'var(--green-600)' : 'var(--red-600)' }}
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
        purpose="基于历史数据回放策略规则，计算 CAGR / Sharpe / 最大回撤 / 胜率等指标。在实盘前验证策略可行性。"
        flow={[
          { to: '/review', label: '复盘' },
          { label: '回测' },
        ]}
        actions={
          <Button
            type="primary"
            size="large"
            icon={<PlayCircleOutlined />}
            onClick={handleSubmit}
            loading={submitM.isPending}
          >
            运行回测
          </Button>
        }
      />

      <PageSection title="回测配置">
        <Form<ConfigFormValues>
          form={form}
          layout="vertical"
          initialValues={{ initial_capital: 1_000_000, slippage_bps: 10 }}
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

          <Divider style={{ margin: 'var(--sp-2) 0 var(--sp-4)' }} />

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
              style={{ fontFamily: 'var(--font-numeric)', fontSize: 'var(--fs-xs)' }}
            />
          </Form.Item>

          <Button
            type="primary"
            size="large"
            icon={<PlayCircleOutlined />}
            onClick={handleSubmit}
            loading={submitM.isPending}
          >
            运行回测
          </Button>
        </Form>
      </PageSection>

      {result?.status === 'completed' && result.result_json && metrics && (
        <>
          <PageSection title="核心指标">
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                gap: 'var(--sp-3)',
              }}
            >
              <StatCard
                label="总收益"
                value={formatPercent(metrics.total_return)}
                delta={
                  metrics.total_return !== 0
                    ? {
                        value: formatPercent(metrics.total_return, 1),
                        direction: metrics.total_return >= 0 ? 'up' : 'down',
                      }
                    : undefined
                }
              />
              <StatCard
                label="CAGR"
                value={formatPercent(metrics.cagr)}
                delta={
                  metrics.cagr !== 0
                    ? {
                        value: formatPercent(metrics.cagr, 1),
                        direction: metrics.cagr >= 0 ? 'up' : 'down',
                      }
                    : undefined
                }
              />
              <StatCard label="Sharpe" value={metrics.sharpe.toFixed(2)} />
              <StatCard
                label="最大回撤"
                value={formatPercent(metrics.max_drawdown)}
                delta={{
                  value: formatPercent(metrics.max_drawdown, 1),
                  direction: metrics.max_drawdown > 0 ? 'down' : 'up',
                  good: 'up',
                }}
              />
              <StatCard
                label="胜率"
                value={`${(metrics.win_rate * 100).toFixed(1)}%`}
              />
              <StatCard label="交易次数" value={metrics.trade_count} />
              {metrics.alpha != null && (
                <StatCard
                  label="Alpha (vs 基准)"
                  value={formatPercent(metrics.alpha)}
                  delta={
                    metrics.alpha !== 0
                      ? {
                          value: formatPercent(metrics.alpha, 1),
                          direction: metrics.alpha >= 0 ? 'up' : 'down',
                        }
                      : undefined
                  }
                />
              )}
            </div>
            <Divider style={{ margin: 'var(--sp-4) 0 var(--sp-3)' }} />
            <Space size="large" wrap>
              <Text type="secondary">
                最终现金: <strong className="num">{formatCurrency(result.result_json.final_cash)}</strong>
              </Text>
              <Text type="secondary">
                持仓数量:{' '}
                <strong className="num">
                  {Object.keys(result.result_json.final_positions).length}
                </strong>{' '}
                只
              </Text>
              <Text type="secondary">
                基准收益: <strong className="num">{formatPercent(metrics.benchmark_return)}</strong>
              </Text>
            </Space>
          </PageSection>

          {equityOption && (
            <PageSection title="净值曲线">
              <ReactECharts
                echarts={echarts}
                option={equityOption}
                style={{ height: 400 }}
                notMerge
              />
            </PageSection>
          )}

          <PageSection title="月度收益">
            <MonthlyReturnsTable monthly={result.result_json.monthly_returns} />
          </PageSection>

          <PageSection title="信号明细">
            <Table<TradeRecord>
              size="small"
              dataSource={result.result_json.trades_log}
              rowKey={(_, idx) => String(idx)}
              columns={tradeColumns}
              pagination={{ pageSize: 20, showSizeChanger: true }}
              scroll={{ x: 760 }}
            />
          </PageSection>
        </>
      )}

      {result?.status === 'failed' && (
        <PageSection title="回测失败">
          <Paragraph type="danger" style={{ marginBottom: 0 }}>
            {result.error_message || '未知错误'}
          </Paragraph>
        </PageSection>
      )}

      <PageSection title="历史回测">
        <QueryBoundary query={historyQ}>
          {() => (
            <>
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
              <Text type="secondary" style={{ fontSize: 'var(--fs-xs)' }}>
                点击行可重新展示该回测结果
              </Text>
            </>
          )}
        </QueryBoundary>
      </PageSection>
    </div>
  );
}
