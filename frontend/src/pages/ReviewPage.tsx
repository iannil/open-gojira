/**
 * Review — autopilot's "事后一刀两断" view.
 *
 * Monthly aggregator over the audit_log:
 *  - draft hit rate (executed / triggered) + breakdown by side
 *  - plan churn (created / invalidated / status changes)
 *  - holdings activity
 *  - top stocks by draft volume
 *  - audit-log timeline for the chosen month
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  InputNumber,
  Row,
  Space,
  Spin,
  Statistic,
  Table,
  Tabs,
  Tag,
  Timeline,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs, { Dayjs } from 'dayjs';

import { fetchAnnualReview, fetchMonthlyReview, fetchQuarterlyReview } from '../api/client';
import PageHeader from '../components/PageHeader';
import type { QuarterlyReview as QuarterlyReviewType, AnnualReview as AnnualReviewType, ReviewByStock, ReviewEntry, ReviewResponse } from '../api/types';

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
    },
  ];
  return (
    <Card title={`本月草稿活动 Top ${data.length}`}>
      {data.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无草稿" />
      ) : (
        <Table
          dataSource={data}
          columns={columns}
          rowKey="stock_code"
          pagination={false}
          size="small"
        />
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
    extreme_low: '#52c41a',
    low: '#73d13d',
    mid: '#faad14',
    high: '#fa8c16',
    extreme_high: '#cf1322',
  };
  const pos = cycle.cycle_position;
  return (
    <Card title="市场周期位置" size="small">
      <Space orientation="vertical" size={8} style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text strong style={{ fontSize: 16, color: positionColor[pos] ?? '#666' }}>
            {positionLabel[pos] ?? pos}
          </Text>
          {cycle.pe_pct_10y != null && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              沪深300 PE 分位 {cycle.pe_pct_10y.toFixed(1)}%
            </Text>
          )}
        </div>
        <Text type="secondary" style={{ fontSize: 13 }}>
          {cycle.position_advice}
        </Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          建议仓位范围 {(cycle.position_range[0] * 100).toFixed(0)}% – {(cycle.position_range[1] * 100).toFixed(0)}%
        </Text>
      </Space>
    </Card>
  );
}

function ThesisAlertsCard({ alerts }: { alerts: ReviewResponse['thesis_alerts'] }) {
  if (alerts.length === 0) {
    return (
      <Card title="论点变量监控" size="small">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无越界论点变量" />
      </Card>
    );
  }
  return (
    <Card
      title={`论点变量告警（${alerts.length}）`}
      size="small"
      extra={<Tag color="red">需关注</Tag>}
    >
      <Space orientation="vertical" size={6} style={{ width: '100%' }}>
        {alerts.map((a, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
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
      <Card title="时间轴">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本月无事件" />
      </Card>
    );
  }
  return (
    <Card title={`时间轴（最近 ${entries.length} 条）`}>
      <Timeline
        mode="left"
        items={entries.map((entry) => ({
          color: entryColor(entry),
          label: entry.created_at
            ? dayjs(entry.created_at).format('MM-DD HH:mm')
            : '—',
          children: (
            <Space orientation="vertical" size={2}>
              <Space size={6}>
                <Tag color={entryColor(entry)}>
                  {ENTITY_LABEL[entry.entity_type] ?? entry.entity_type}
                  {' · '}
                  {EVENT_LABEL[entry.event] ?? entry.event}
                </Tag>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {ACTOR_LABEL[entry.actor] ?? entry.actor}
                </Text>
                {entry.stock_code && (
                  <Link to={`/stock/${entry.stock_code}`}>
                    {entry.stock_code}
                  </Link>
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
  const [data, setData] = useState<QuarterlyReviewType | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchQuarterlyReview(year, q));
    } catch { /* ignore */ }
    setLoading(false);
  }, [year, q]);

  useEffect(() => { void refresh(); }, [refresh]);

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <InputNumber min={2020} max={2030} value={year} onChange={(v) => v && setYear(v)} />
        <Space>
          {[1, 2, 3, 4].map((i) => (
            <Button key={i} size="small" type={q === i ? 'primary' : 'default'} onClick={() => setQ(i)}>
              Q{i}
            </Button>
          ))}
        </Space>
        <Button onClick={refresh} loading={loading}>刷新</Button>
      </Space>
      {loading && !data ? <Spin /> : data ? (
        <Row gutter={16}>
          <Col xs={12} md={6}>
            <Card><Statistic title="预案成功率" value={data.plan_success_rate ?? 0} suffix="%" precision={1} /></Card>
          </Col>
          <Col xs={12} md={6}>
            <Card><Statistic title="草稿 执行/取消" value={`${data.drafts_executed} / ${data.drafts_cancelled}`} /></Card>
          </Col>
          <Col xs={12} md={6}>
            <Card><Statistic title="纪律评分" value={data.discipline_score ?? 0} suffix="%" precision={1} /></Card>
          </Col>
          <Col xs={12} md={6}>
            <Card><Statistic title="主题对齐" value={data.theme_alignment_pct} suffix="%" precision={1} /></Card>
          </Col>
        </Row>
      ) : <Empty />}
    </div>
  );
}

function AnnualTab() {
  const [year, setYear] = useState(dayjs().year());
  const [data, setData] = useState<AnnualReviewType | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchAnnualReview(year));
    } catch { /* ignore */ }
    setLoading(false);
  }, [year]);

  useEffect(() => { void refresh(); }, [refresh]);

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <InputNumber min={2020} max={2030} value={year} onChange={(v) => v && setYear(v)} />
        <Button onClick={refresh} loading={loading}>刷新</Button>
      </Space>
      {loading && !data ? <Spin /> : data ? (
        <>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col xs={12} md={6}>
              <Card><Statistic title="目标进度" value={data.goal_progress_pct ?? 0} suffix="%" precision={1} /></Card>
            </Col>
            <Col xs={12} md={6}>
              <Card><Statistic title="全年执行/取消" value={`${data.total_executed} / ${data.total_cancelled}`} /></Card>
            </Col>
            <Col xs={12} md={6}>
              <Card><Statistic title="股息记录数" value={data.dividend_records_count} /></Card>
            </Col>
            <Col xs={12} md={6}>
              <Card><Statistic title="股息收入估算" value={data.dividend_income_estimate} precision={2} /></Card>
            </Col>
          </Row>
          <Row gutter={16}>
            {data.quarters.map((qr, idx) => (
              <Col key={idx} xs={12} md={6}>
                <Card size="small" title={qr.period}>
                  <Statistic title="预案成功率" value={qr.plan_success_rate ?? 0} suffix="%" precision={1} />
                  <Statistic title="执行" value={qr.drafts_executed} valueStyle={{ fontSize: 14 }} />
                </Card>
              </Col>
            ))}
          </Row>
        </>
      ) : <Empty />}
    </div>
  );
}

export default function ReviewPage() {
  const [month, setMonth] = useState<Dayjs>(dayjs().startOf('month'));
  const [data, setData] = useState<ReviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (m: Dayjs) => {
    try {
      setLoading(true);
      const payload = await fetchMonthlyReview({
        month: m.format('YYYY-MM'),
      });
      setData(payload);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh(month);
  }, [refresh, month]);

  const hitRateColor = useMemo(() => {
    const hr = data?.drafts.hit_rate;
    if (hr == null) return undefined;
    if (hr >= 0.7) return '#52c41a';
    if (hr >= 0.3) return '#faad14';
    return '#cf1322';
  }, [data]);

  const monthlyContent = (
    <>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Space>
          <Text type="secondary" style={{ fontSize: 12 }}>选择月份</Text>
          <DatePicker
            picker="month"
            value={month}
            allowClear={false}
            onChange={(v) => v && setMonth(v.startOf('month'))}
          />
          <Button onClick={() => void refresh(month)}>刷新</Button>
        </Space>
      </div>

      {error && (
        <Alert type="error" showIcon style={{ marginBottom: 16 }} message="加载失败" description={error} />
      )}

      {loading && !data ? (
        <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
      ) : data ? (
        <>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col xs={12} md={6}>
              <Card>
                <Statistic title="草稿命中率" value={data.drafts.hit_rate != null ? data.drafts.hit_rate * 100 : 0} precision={1} suffix="%" styles={{ content: { color: hitRateColor } }} />
                <Text type="secondary" style={{ fontSize: 12 }}>{data.drafts.executed} / {data.drafts.triggered} 已成交</Text>
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card>
                <Statistic title="买入 / 卖出" value={`${data.drafts.buy} / ${data.drafts.sell}`} />
                <Text type="secondary" style={{ fontSize: 12 }}>本月触发的草稿方向</Text>
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card>
                <Statistic title="新建 / 失效预案" value={`${data.plans.created} / ${data.plans.invalidated}`} />
                <Text type="secondary" style={{ fontSize: 12 }}>状态变更 {data.plans.status_changed} 次</Text>
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card>
                <Statistic title="持仓买入 / 卖出" value={`${data.holdings.created} / ${data.holdings.sold}`} />
                <Text type="secondary" style={{ fontSize: 12 }}>本月真实成交回填</Text>
              </Card>
            </Col>
          </Row>

          {(data.cycle || data.thesis_alerts.length > 0) && (
            <Row gutter={16} style={{ marginBottom: 16 }}>
              {data.cycle && <Col xs={24} md={12}><CycleCard cycle={data.cycle} /></Col>}
              {data.thesis_alerts.length > 0 && <Col xs={24} md={12}><ThesisAlertsCard alerts={data.thesis_alerts} /></Col>}
            </Row>
          )}

          <Row gutter={16}>
            <Col xs={24} lg={9}><StockTable data={data.by_stock} /></Col>
            <Col xs={24} lg={15}><EntryTimeline entries={data.entries} /></Col>
          </Row>

          {data.cashflow_goal_updates > 0 && (
            <Text type="secondary" style={{ display: 'block', marginTop: 12, fontSize: 12 }}>· 本月更新过 {data.cashflow_goal_updates} 次现金流目标</Text>
          )}

          <Text type="secondary" style={{ display: 'block', marginTop: 8, fontSize: 12 }}>
            草稿命中率 = <code>已成交 / 触发</code>，&lt; 30% 说明 gates 太松或 ladder 阈值过激，应回顾预案；命中率 = {formatPct(data.drafts.hit_rate)}。
          </Text>
        </>
      ) : null}
    </>
  );

  return (
    <div>
      <PageHeader title="复盘" enLabel="Review" />
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
