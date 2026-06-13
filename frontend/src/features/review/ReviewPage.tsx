import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  InputNumber,
  Row,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Timeline,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs, { Dayjs } from 'dayjs';

import { PageHeader, StatCard } from '../../components/primitives';
import QueryBoundary from '../../components/QueryBoundary';
import {
  useAnnualReviewQuery,
  useMonthlyReviewQuery,
  useQuarterlyReviewQuery,
} from './useReviewQueries';
import type {
  AnnualReview as AnnualReviewType,
  QuarterlyReview as QuarterlyReviewType,
  ReviewByStock,
  ReviewEntry,
  ReviewResponse,
} from '../../api/types';

const { Text } = Typography;

function formatPct(decimal: number | null | undefined, digits = 1): string {
  if (decimal == null) return '—';
  return `${(decimal * 100).toFixed(digits)}%`;
}

const ENTITY_LABEL: Record<string, string> = {
  draft: '草稿',
  plan: '预案',
  plan_template: '模板',
  holding: '持仓',
  cashflow_goal: '目标',
  alert: '告警',
  stock: '标的',
};

const EVENT_LABEL: Record<string, string> = {
  triggered: '触发',
  executed: '执行',
  cancelled: '取消',
  created: '创建',
  updated: '更新',
  invalidated: '撤销',
  status_changed: '状态变更',
  sold: '卖出',
  blocked_by_portfolio_constraint: '仓位阻断',
};

const ACTOR_LABEL: Record<string, string> = {
  user: '用户',
  evaluator: '系统',
  scheduler: '调度',
};

const EVENT_COLOR: Record<string, string> = {
  triggered: 'blue',
  executed: 'green',
  cancelled: 'red',
  created: 'cyan',
  updated: 'gold',
  invalidated: 'red',
  status_changed: 'purple',
  sold: 'volcano',
};

function entryColor(entry: ReviewEntry): string {
  return EVENT_COLOR[entry.event] || 'gray';
}

function StockTable({ data }: { data: ReviewByStock[] }) {
  const columns: ColumnsType<ReviewByStock> = [
    {
      title: '代码',
      dataIndex: 'stock_code',
      render: (code: string) => <Link to={`/stock/${code}`}>{code}</Link>,
    },
    {
      title: '草稿数',
      dataIndex: 'drafts_triggered',
      align: 'right',
      render: (v: number) => <span className="num">{v}</span>,
    },
  ];
  return (
    <Card className="gojira-card" bordered={false} title={`本月草稿活动 Top ${data.length}`}>
      {data.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无草稿" />
      ) : (
        <Table dataSource={data} columns={columns} rowKey="stock_code" pagination={false} size="small" />
      )}
    </Card>
  );
}

function CycleCard({ cycle }: { cycle: NonNullable<ReviewResponse['cycle']> }) {
  const positionLabel: Record<string, string> = {
    extreme_low: '极度低估',
    low: '低估',
    mid: '中等',
    high: '偏高',
    extreme_high: '极度高估',
  };
  const positionColor: Record<string, string> = {
    extreme_low: 'var(--green-600)',
    low: 'var(--green-500)',
    mid: 'var(--amber-600)',
    high: 'var(--amber-500)',
    extreme_high: 'var(--red-600)',
  };
  const pos = cycle.cycle_position;
  return (
    <Card className="gojira-card" bordered={false} title="市场周期位置" size="small">
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text strong style={{ fontSize: 'var(--fs-md)', color: positionColor[pos] ?? 'var(--text-primary)' }}>
            {positionLabel[pos] ?? pos}
          </Text>
          {cycle.pe_pct_10y != null && (
            <Text type="secondary" style={{ fontSize: 'var(--fs-xs)' }}>
              沪深300 PE 分位 <span className="num">{cycle.pe_pct_10y.toFixed(1)}%</span>
            </Text>
          )}
        </div>
        <Text type="secondary" style={{ fontSize: 'var(--fs-sm)' }}>
          {cycle.position_advice}
        </Text>
        <Text type="secondary" style={{ fontSize: 'var(--fs-xs)' }}>
          建议仓位范围 <span className="num">{(cycle.position_range[0] * 100).toFixed(0)}%</span> –{' '}
          <span className="num">{(cycle.position_range[1] * 100).toFixed(0)}%</span>
        </Text>
      </Space>
    </Card>
  );
}

function ThesisAlertsCard({ alerts }: { alerts: ReviewResponse['thesis_alerts'] }) {
  if (alerts.length === 0) {
    return (
      <Card className="gojira-card" bordered={false} title="论点变量监控" size="small">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无越界论点变量" />
      </Card>
    );
  }
  return (
    <Card
      className="gojira-card"
      bordered={false}
      title={`论点变量告警（${alerts.length}）`}
      size="small"
      extra={<Tag color="red">需关注</Tag>}
    >
      <Space direction="vertical" size={6} style={{ width: '100%' }}>
        {alerts.map((a, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
            <Tag color={a.threshold_type === 'critical' ? 'red' : 'orange'}>
              {a.threshold_type === 'critical' ? '严重' : '警告'}
            </Tag>
            <Link to={`/stock/${a.code}`}>
              <Text strong>{a.code}</Text>
            </Link>
            <Text>{a.variable_name}</Text>
            <Text type="secondary">{a.message}</Text>
          </div>
        ))}
      </Space>
    </Card>
  );
}

function EntryTimeline({ entries }: { entries: ReviewEntry[] }) {
  if (entries.length === 0) {
    return (
      <Card className="gojira-card" bordered={false} title="时间轴">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本月无事件" />
      </Card>
    );
  }
  return (
    <Card className="gojira-card" bordered={false} title={`时间轴（最近 ${entries.length} 条）`}>
      <Timeline
        mode="left"
        items={entries.map((entry) => ({
          color: entryColor(entry),
          label: entry.created_at ? (
            <span className="num">{dayjs(entry.created_at).format('MM-DD HH:mm')}</span>
          ) : (
            '—'
          ),
          children: (
            <Space direction="vertical" size={2}>
              <Space size={6} wrap>
                <Tag color={entryColor(entry)}>
                  {ENTITY_LABEL[entry.entity_type] ?? entry.entity_type}
                  {' · '}
                  {EVENT_LABEL[entry.event] ?? entry.event}
                </Tag>
                <Text type="secondary" style={{ fontSize: 'var(--fs-xs)' }}>
                  {ACTOR_LABEL[entry.actor] ?? entry.actor}
                </Text>
                {entry.stock_code && (
                  <Link to={`/stock/${entry.stock_code}`}>{entry.stock_code}</Link>
                )}
              </Space>
              <Text>{entry.summary}</Text>
            </Space>
          ),
        }))}
      />
    </Card>
  );
}

function QuarterlyTab() {
  const [year, setYear] = useState(dayjs().year());
  const [q, setQ] = useState(Math.ceil((dayjs().month() + 1) / 3));
  const qQ = useQuarterlyReviewQuery(year, q);

  return (
    <div>
      <Space style={{ marginBottom: 'var(--sp-4)' }}>
        <InputNumber min={2020} max={2030} value={year} onChange={(v) => v && setYear(v)} />
        <Space>
          {[1, 2, 3, 4].map((i) => (
            <Button
              key={i}
              size="small"
              type={q === i ? 'primary' : 'default'}
              onClick={() => setQ(i)}
            >
              Q{i}
            </Button>
          ))}
        </Space>
        <Button onClick={() => qQ.refetch()} loading={qQ.isFetching}>
          刷新
        </Button>
      </Space>
      <QueryBoundary query={qQ}>
        {(data: QuarterlyReviewType) => (
          <Row gutter={16}>
            <Col xs={12} md={6}>
              <StatCard
                label="预案成功率"
                value={`${(data.plan_success_rate ?? 0).toFixed(1)}%`}
              />
            </Col>
            <Col xs={12} md={6}>
              <StatCard
                label="草稿 执行/取消"
                value={`${data.drafts_executed} / ${data.drafts_cancelled}`}
              />
            </Col>
            <Col xs={12} md={6}>
              <StatCard
                label="纪律评分"
                value={`${(data.discipline_score ?? 0).toFixed(1)}%`}
              />
            </Col>
            <Col xs={12} md={6}>
              <StatCard
                label="主题对齐"
                value={`${data.theme_alignment_pct.toFixed(1)}%`}
              />
            </Col>
          </Row>
        )}
      </QueryBoundary>
    </div>
  );
}

function AnnualTab() {
  const [year, setYear] = useState(dayjs().year());
  const q = useAnnualReviewQuery(year);

  return (
    <div>
      <Space style={{ marginBottom: 'var(--sp-4)' }}>
        <InputNumber min={2020} max={2030} value={year} onChange={(v) => v && setYear(v)} />
        <Button onClick={() => q.refetch()} loading={q.isFetching}>
          刷新
        </Button>
      </Space>
      <QueryBoundary query={q}>
        {(data: AnnualReviewType) => (
          <>
            <Row gutter={16} style={{ marginBottom: 'var(--sp-4)' }}>
              <Col xs={12} md={6}>
                <StatCard label="目标进度" value={`${(data.goal_progress_pct ?? 0).toFixed(1)}%`} />
              </Col>
              <Col xs={12} md={6}>
                <StatCard
                  label="全年执行/取消"
                  value={`${data.total_executed} / ${data.total_cancelled}`}
                />
              </Col>
              <Col xs={12} md={6}>
                <StatCard label="股息记录数" value={data.dividend_records_count} />
              </Col>
              <Col xs={12} md={6}>
                <StatCard
                  label="股息收入估算"
                  value={data.dividend_income_estimate.toFixed(2)}
                />
              </Col>
            </Row>
            <Row gutter={16}>
              {data.quarters.map((qr, idx) => (
                <Col key={idx} xs={12} md={6}>
                  <Card className="gojira-card" bordered={false} size="small" title={qr.period}>
                    <Statistic
                      title="预案成功率"
                      value={qr.plan_success_rate ?? 0}
                      suffix="%"
                      precision={1}
                    />
                    <Statistic
                      title="执行"
                      value={qr.drafts_executed}
                      valueStyle={{ fontSize: 'var(--fs-sm)' }}
                    />
                  </Card>
                </Col>
              ))}
            </Row>
          </>
        )}
      </QueryBoundary>
    </div>
  );
}

export default function ReviewPage() {
  const [month, setMonth] = useState<Dayjs>(dayjs().startOf('month'));
  const monthQ = useMonthlyReviewQuery(month.format('YYYY-MM'));
  const data = monthQ.data;

  const hitRateColor = useMemo(() => {
    const hr = data?.drafts.hit_rate;
    if (hr == null) return undefined;
    if (hr >= 0.7) return 'var(--green-600)';
    if (hr >= 0.3) return 'var(--amber-600)';
    return 'var(--red-600)';
  }, [data]);

  const monthlyContent = (
    <>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 'var(--sp-4)' }}>
        <Space>
          <Text type="secondary" style={{ fontSize: 'var(--fs-xs)' }}>
            选择月份
          </Text>
          <DatePicker
            picker="month"
            value={month}
            allowClear={false}
            onChange={(v) => v && setMonth(v.startOf('month'))}
          />
          <Button onClick={() => monthQ.refetch()} loading={monthQ.isFetching}>
            刷新
          </Button>
        </Space>
      </div>

      <QueryBoundary query={monthQ}>
        {(d: ReviewResponse) => (
          <>
            <Row gutter={16} style={{ marginBottom: 'var(--sp-4)' }}>
              <Col xs={12} md={6}>
                <StatCard
                  label="草稿命中率"
                  value={`${d.drafts.hit_rate != null ? (d.drafts.hit_rate * 100).toFixed(1) : '0'}%`}
                  hint={`${d.drafts.executed} / ${d.drafts.triggered} 已成交`}
                />
                {hitRateColor && (
                  <div
                    style={{
                      fontSize: 'var(--fs-xs)',
                      color: hitRateColor,
                      marginTop: 4,
                    }}
                  >
                    {d.drafts.hit_rate! >= 0.7
                      ? '✓ 良好'
                      : d.drafts.hit_rate! >= 0.3
                        ? '⚠ 中等'
                        : '✗ 偏低'}
                  </div>
                )}
              </Col>
              <Col xs={12} md={6}>
                <StatCard
                  label="买入 / 卖出"
                  value={`${d.drafts.buy} / ${d.drafts.sell}`}
                  hint="本月触发的草稿方向"
                />
              </Col>
              <Col xs={12} md={6}>
                <StatCard
                  label="新建 / 失效预案"
                  value={`${d.plans.created} / ${d.plans.invalidated}`}
                  hint={`状态变更 ${d.plans.status_changed} 次`}
                />
              </Col>
              <Col xs={12} md={6}>
                <StatCard
                  label="持仓买入 / 卖出"
                  value={`${d.holdings.created} / ${d.holdings.sold}`}
                  hint="本月真实成交回填"
                />
              </Col>
            </Row>

            {(d.cycle || d.thesis_alerts.length > 0) && (
              <Row gutter={16} style={{ marginBottom: 'var(--sp-4)' }}>
                {d.cycle && (
                  <Col xs={24} md={12}>
                    <CycleCard cycle={d.cycle} />
                  </Col>
                )}
                {d.thesis_alerts.length > 0 && (
                  <Col xs={24} md={12}>
                    <ThesisAlertsCard alerts={d.thesis_alerts} />
                  </Col>
                )}
              </Row>
            )}

            <Row gutter={16}>
              <Col xs={24} lg={9}>
                <StockTable data={d.by_stock} />
              </Col>
              <Col xs={24} lg={15}>
                <EntryTimeline entries={d.entries} />
              </Col>
            </Row>

            {d.cashflow_goal_updates > 0 && (
              <Text
                type="secondary"
                style={{ display: 'block', marginTop: 'var(--sp-3)', fontSize: 'var(--fs-xs)' }}
              >
                · 本月更新过 <span className="num">{d.cashflow_goal_updates}</span> 次现金流目标
              </Text>
            )}

            <Text
              type="secondary"
              style={{ display: 'block', marginTop: 8, fontSize: 'var(--fs-xs)' }}
            >
              草稿命中率 = <code>已成交 / 触发</code>，&lt; 30% 说明 gates 太松或 ladder 阈值过激，应回顾预案；命中率 ={' '}
              {formatPct(d.drafts.hit_rate)}。
            </Text>
          </>
        )}
      </QueryBoundary>
    </>
  );

  return (
    <div>
      <PageHeader
        title="复盘"
        enLabel="Review"
        purpose="事后审计：草稿命中率、预案表现、市场周期、论点告警。命中率 < 30% 说明 gates 太松，需要调预案。"
        flow={[
          { to: '/trades', label: '成交流水' },
          { label: '复盘' },
          { to: '/backtest', label: '回测' },
        ]}
      />
      <Tabs
        defaultActiveKey="monthly"
        items={[
          { key: 'monthly', label: '月度', children: monthlyContent },
          { key: 'quarterly', label: '季度', children: <QuarterlyTab /> },
          { key: 'annual', label: '年度', children: <AnnualTab /> },
        ]}
      />
    </div>
  );
}
