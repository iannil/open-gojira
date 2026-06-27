import { Link } from 'react-router-dom';
import {
  Card,
  Col,
  Row,
  Statistic,
  Table,
  Typography,
} from 'antd';
import {
  BarChartOutlined,
  DollarOutlined,
  PieChartOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';

import type { HoldingResponse, PortfolioSummary } from '../../api/types';
import { PageHeader } from '../../components/primitives';
import PageSection from '../../components/primitives/PageSection';
import QueryBoundary from '../../components/QueryBoundary';
import { usePortfolioSummaryQuery, usePortfolioEvaluationQuery } from './usePortfolioQueries';

const { Text } = Typography;

function fmtPct(n: number | null | undefined, digits = 2): string {
  return n === null || n === undefined ? '—' : `${n.toFixed(digits)}%`;
}

function fmtCurrency(n: number | null | undefined): string {
  return n === null || n === undefined ? '—' : `¥${n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtDecimal(n: number | null | undefined, digits = 2): string {
  return n === null || n === undefined ? '—' : n.toFixed(digits);
}

const HOLDING_COLUMNS: ColumnsType<HoldingResponse> = [
  {
    title: '股票',
    dataIndex: 'stock_code',
    width: 100,
    render: (code: string) => <Link to={`/stock/${code}`}><Text code>{code}</Text></Link>,
  },
  { title: '名称', dataIndex: 'stock_name', width: 120, ellipsis: true },
  { title: '行业', dataIndex: 'stock_industry', width: 100, ellipsis: true },
  {
    title: '持仓量',
    dataIndex: 'quantity',
    width: 100,
    align: 'right',
    render: (q: number) => q.toLocaleString('zh-CN'),
  },
  {
    title: '成本价',
    dataIndex: 'buy_price',
    width: 100,
    align: 'right',
    render: (p: number) => fmtCurrency(p),
  },
  {
    title: '现值',
    dataIndex: 'current_value',
    width: 100,
    align: 'right',
    render: (v: number | null) => fmtCurrency(v),
  },
  {
    title: '盈亏',
    dataIndex: 'pnl',
    width: 120,
    align: 'right',
    render: (pnl: number | null) => (
      <Text style={{ color: pnl !== null && pnl >= 0 ? '#cf1322' : '#3f8600' }}>
        {fmtCurrency(pnl)}
      </Text>
    ),
  },
  {
    title: '盈亏%',
    dataIndex: 'pnl_pct',
    width: 100,
    align: 'right',
    render: (p: number | null) => (
      <Text style={{ color: p !== null && p >= 0 ? '#cf1322' : '#3f8600' }}>
        {fmtPct(p)}
      </Text>
    ),
  },
  {
    title: '年化%',
    dataIndex: 'annualized_return_pct',
    width: 100,
    align: 'right',
    render: (p: number | null) => (
      <Text style={{ color: p !== null && p >= 0 ? '#cf1322' : '#3f8600' }}>
        {fmtPct(p)}
      </Text>
    ),
  },
  {
    title: '权重%',
    dataIndex: 'weight_pct',
    width: 80,
    align: 'right',
    render: (w: number | null) => fmtDecimal(w, 1),
  },
];

function SummaryCards({ summary }: { summary: PortfolioSummary }) {
  const pnlColor = summary.total_pnl_pct !== null
    ? summary.total_pnl_pct >= 0 ? '#cf1322' : '#3f8600'
    : undefined;

  return (
    <Row gutter={16}>
      <Col span={6}>
        <Card>
          <Statistic
            title="持仓数"
            value={summary.position_count}
            prefix={<PieChartOutlined />}
          />
        </Card>
      </Col>
      <Col span={6}>
        <Card>
          <Statistic
            title="组合市值"
            value={summary.total_value}
            precision={0}
            prefix="¥"
          />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            成本 ¥{summary.total_cost.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
          </Typography.Text>
        </Card>
      </Col>
      <Col span={6}>
        <Card>
          <Statistic
            title="累计盈亏"
            value={summary.total_pnl ?? 0}
            precision={2}
            prefix="¥"
            suffix={`(${summary.total_pnl_pct?.toFixed(2) ?? '—'}%)`}
            valueStyle={{ color: pnlColor }}
          />
          {summary.portfolio_annualized_pct !== null && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              年化 {summary.portfolio_annualized_pct.toFixed(2)}%
            </Typography.Text>
          )}
        </Card>
      </Col>
      <Col span={6}>
        <Card>
          <Statistic
            title="现金占比"
            value={summary.cash_ratio_pct}
            precision={1}
            suffix="%"
          />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            现金 ¥{summary.cash_reserve.toLocaleString('zh-CN')}
          </Typography.Text>
        </Card>
      </Col>
    </Row>
  );
}

function EvaluationSection() {
  const evQ = usePortfolioEvaluationQuery();

  return (
    <QueryBoundary query={evQ} isEmpty={(d) => !d}>
      {() => {
        const ev = evQ.data!;
        return (
          <PageSection
            title={<><BarChartOutlined /> 组合评价</>}
            subtitle="基准对比 · 交易统计 · 信号质量"
          >
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small" title="组合收益">
            <Statistic value={ev.benchmark.portfolio_return_pct ?? '—'} precision={2} suffix="%" />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" title={`vs ${ev.benchmark.benchmark_name}`}>
            <Statistic value={ev.benchmark.benchmark_return_pct ?? '—'} precision={2} suffix="%"
              valueStyle={{ color: '#1890ff' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" title="超额收益">
            <Statistic value={ev.benchmark.excess_return_pct ?? '—'} precision={2} suffix="%"
              valueStyle={{ color: (ev.benchmark.excess_return_pct ?? 0) >= 0 ? '#52c41a' : '#ff4d4f' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" title="夏普比率">
            <Statistic value={ev.sharpe_ratio ?? '—'} precision={3} />
          </Card>
        </Col>
      </Row>
      <Row gutter={16}>
        <Col span={6}>
          <Card size="small" title="胜率">
            <Statistic value={ev.trade_stats.win_rate_pct} suffix="%" precision={1} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" title="交易次数">
            <Statistic value={ev.trade_stats.total_trades} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" title="Profit Factor">
            <Statistic value={ev.trade_stats.profit_factor} precision={2} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" title="平均滑点">
            <Statistic value={ev.signal_quality.avg_slippage_pct} suffix="%" precision={3} />
          </Card>
        </Col>
      </Row>
    </PageSection>
          );
        }}
      </QueryBoundary>
  );
}

export default function PortfolioPage() {
  const summaryQ = usePortfolioSummaryQuery();

  return (
    <div>
      <PageHeader
        title="持仓组合"
        enLabel="Portfolio"
        purpose="当前持仓总览：市值、盈亏、权重分布。持仓完全从 Trade 账本派生。"
        flow={[
          { to: '/portfolio', label: '持仓组合' },
          { to: '/trades', label: '成交流水' },
        ]}
      />

      <QueryBoundary
        query={summaryQ}
        isEmpty={(data) => data.holdings.length === 0}
        emptyRender={
          <PageSection title="持仓列表">
            <Text type="secondary">暂无持仓。通过录入交易或导入 CSV 建立持仓。</Text>
          </PageSection>
        }
      >
        {() => {
          const summary = summaryQ.data!;

          return (
            <>
              {/* 组合评价 */}
              <EvaluationSection />

              {/* 汇总指标 */}
              <PageSection title={<><DollarOutlined /> 汇总指标</>}>
                <SummaryCards summary={summary} />
              </PageSection>

              {/* 告警 */}
              {summary.warnings.length > 0 && (
                <PageSection title={<><WarningOutlined /> 告警</>}>
                  {summary.warnings.map((w, i) => (
                    <Text key={i} type="warning" style={{ display: 'block' }}>
                      {w}
                    </Text>
                  ))}
                </PageSection>
              )}

              {/* 持仓明细 */}
              <PageSection
                title={<><BarChartOutlined /> 持仓明细</>}
                subtitle={`${summary.holdings.length} 只标的`}
              >
                <Table<HoldingResponse>
                  columns={HOLDING_COLUMNS}
                  dataSource={summary.holdings}
                  rowKey={(h) => h.stock_code}
                  size="small"
                  pagination={{ pageSize: 20, size: 'small' }}
                  scroll={{ x: 1100 }}
                />
              </PageSection>
            </>
          );
        }}
      </QueryBoundary>
    </div>
  );
}
