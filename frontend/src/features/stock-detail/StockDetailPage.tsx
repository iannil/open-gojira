import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd';
import { useQuery } from '@tanstack/react-query';

import { PageHeader, PageSection, StatCard, EmptyState } from '../../components/primitives';
import KlineChart from '../../components/stock/KlineChart';
import QiuScorerWizard from '../../components/QiuScorerWizard';
import { listWatchlistGroups } from '../../api/client';
import {
  useMarginTradingQuery,
  useNorthFlowQuery,
  useRevenueCompositionQuery,
  useShareholdersQuery,
  useStockCandidatesQuery,
  useStockHoldingsQuery,
  useStockQuery,
} from './useStockDetailQueries';
import {
  useAddToWatchlistMutation,
  useUpdateThesisVariablesMutation,
} from './useStockDetailMutations';
import ThesisVariablesModal from './components/ThesisVariablesModal';

const { Text } = Typography;

const TIER_COLOR: Record<string, string> = {
  core: 'gold',
  watch: 'blue',
  focus: 'green',
};

const TIER_LABEL: Record<string, string> = {
  core: '核心',
  watch: '关注',
  focus: '重点',
};

export default function StockDetailPage() {
  const { code = '' } = useParams<{ code: string }>();

  const stockQ = useStockQuery(code);
  const candidatesQ = useStockCandidatesQuery(code);
  const holdingsQ = useStockHoldingsQuery(code);
  const shareholdersQ = useShareholdersQuery(code);
  const northQ = useNorthFlowQuery(code);
  const marginQ = useMarginTradingQuery(code);
  const revenueQ = useRevenueCompositionQuery(code);
  const groupsQ = useQuery({
    queryKey: ['watchlist-groups'],
    queryFn: listWatchlistGroups,
    staleTime: 5 * 60_000,
  });

  const thesisM = useUpdateThesisVariablesMutation(code);
  const watchlistM = useAddToWatchlistMutation();

  const [thesisModalOpen, setThesisModalOpen] = useState(false);
  const [qiuModalOpen, setQiuModalOpen] = useState(false);

  const stock = stockQ.data;
  const candidates = candidatesQ.data ?? [];
  const holdings = holdingsQ.data ?? [];
  const shareholders = shareholdersQ.data ?? [];
  const northFlow = northQ.data ?? [];
  const margin = marginQ.data ?? [];
  const revenue = revenueQ.data ?? [];
  const groups = groupsQ.data ?? [];

  // Collect per-section errors so we can surface them as a single banner
  // (matches old behavior). Critical: stockQ error means we can't render.
  if (stockQ.isLoading) {
    return (
      <div style={{ padding: 48, textAlign: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (stockQ.isError || !stock) {
    return (
      <EmptyState
        variant="quiet"
        title={`未找到股票 ${code}`}
      />
    );
  }

  const partialErrors: string[] = [];
  if (shareholdersQ.isError) partialErrors.push('十大股东');
  if (northQ.isError) partialErrors.push('北向资金');
  if (marginQ.isError) partialErrors.push('融资融券');

  const handleAddToWatchlist = async () => {
    if (!groups.length) return;
    await watchlistM.mutateAsync({ groupId: groups[0].id, codes: [code] });
  };

  const shareholderColumns = [
    { title: '日期', dataIndex: 'date' },
    { title: '股东', dataIndex: 'holder_name' },
    { title: '类型', dataIndex: 'holder_type' },
    {
      title: '持股数量',
      dataIndex: 'holding_quantity',
      render: (v: number | null) => (v != null ? <span className="num">{v.toLocaleString()}</span> : '-'),
    },
    {
      title: '持股比例',
      dataIndex: 'holding_ratio',
      render: (v: number | null) =>
        v != null ? <span className="num">{(v * 100).toFixed(2)}%</span> : '-',
    },
  ];

  const northColumns = [
    { title: '日期', dataIndex: 'date' },
    {
      title: '净买入',
      dataIndex: 'net_buy_amount',
      render: (v: number | null) => (v != null ? <span className="num">{v.toLocaleString()}</span> : '-'),
    },
    {
      title: '持股数量',
      dataIndex: 'holding_quantity',
      render: (v: number | null) => (v != null ? <span className="num">{v.toLocaleString()}</span> : '-'),
    },
    {
      title: '持股比例',
      dataIndex: 'holding_ratio',
      render: (v: number | null) =>
        v != null ? <span className="num">{(v * 100).toFixed(2)}%</span> : '-',
    },
  ];

  const marginColumns = [
    { title: '日期', dataIndex: 'date' },
    {
      title: '融资余额',
      dataIndex: 'financing_balance',
      render: (v: number | null) => (v != null ? <span className="num">{v.toLocaleString()}</span> : '-'),
    },
    {
      title: '融券余额',
      dataIndex: 'securities_balance',
      render: (v: number | null) => (v != null ? <span className="num">{v.toLocaleString()}</span> : '-'),
    },
    {
      title: '净融资',
      dataIndex: 'net_financing',
      render: (v: number | null) => (v != null ? <span className="num">{v.toLocaleString()}</span> : '-'),
    },
  ];

  return (
    <div>
      <PageHeader
        title={
          <>
            <code style={{ marginRight: 'var(--sp-3)' }}>{stock.code}</code>
            {stock.name}
          </>
        }
        enLabel="Stock Detail"
        purpose={`${stock.name}（${stock.code}）的详情：基本信息、持仓、变量追踪、K线、股东、北向资金、融资融券、营收构成。`}
      />

      <Space style={{ marginTop: 'var(--sp-2)' }} wrap>
        {stock.industry && <Tag>{stock.industry}</Tag>}
        {stock.tier && (
          <Tag color={TIER_COLOR[stock.tier] ?? 'default'}>
            {TIER_LABEL[stock.tier] ?? stock.tier}
          </Tag>
        )}
        {stock.listed_date && <Tag>上市 {stock.listed_date}</Tag>}
        {candidates.length > 0 && (
          <Tag color="green">候选: {candidates.map((c) => c.plan_name).join(', ')}</Tag>
        )}
      </Space>

      <Space style={{ marginTop: 'var(--sp-3)' }}>
        <Button onClick={handleAddToWatchlist} loading={watchlistM.isPending}>
          加入自选
        </Button>
        <Button onClick={() => setQiuModalOpen(true)}>
          求评分 (<span className="num">{stock.qiu_score ?? 0}</span>/3)
        </Button>
        <Button onClick={() => setThesisModalOpen(true)}>编辑变量</Button>
        <Link to="/plans">
          <Button type="primary">管理预案</Button>
        </Link>
      </Space>

      {partialErrors.length > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 'var(--sp-4)' }}
          message={`部分数据加载失败：${partialErrors.join('、')}`}
        />
      )}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 'var(--sp-3)',
          marginTop: 'var(--sp-4)',
        }}
      >
        <StatCard label="代码" value={stock.code} />
        <StatCard label="行业" value={stock.industry ?? '-'} />
        <StatCard label="持仓笔数" value={holdings.length} />
        <StatCard
          label="候选预案"
          value={candidates.length > 0 ? candidates.map((c) => c.plan_name).join(', ') : '无'}
        />
      </div>

      <div style={{ marginTop: 'var(--sp-4)' }}>
        <PageSection title="基本信息">
          <Descriptions column={1} size="small">
            <Descriptions.Item label="代码">{stock.code}</Descriptions.Item>
            <Descriptions.Item label="名称">{stock.name}</Descriptions.Item>
            <Descriptions.Item label="行业">{stock.industry ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="上市日">{stock.listed_date ?? '-'}</Descriptions.Item>
          </Descriptions>
        </PageSection>
      </div>

      <div style={{ marginTop: 'var(--sp-4)' }}>
        <PageSection title={`当前持仓 (${holdings.length})`}>
          {holdings.length === 0 ? (
            <Empty description="未持仓" />
          ) : (
            <Table
              size="small"
              rowKey="id"
              dataSource={holdings}
              pagination={false}
              columns={[
                { title: '买入日', dataIndex: 'buy_date' },
                {
                  title: '买入价',
                  dataIndex: 'buy_price',
                  render: (v: number) => <span className="num">{v}</span>,
                },
                {
                  title: '数量',
                  dataIndex: 'quantity',
                  render: (v: number) => <span className="num">{v.toLocaleString()}</span>,
                },
                {
                  title: '止盈价',
                  dataIndex: 'stop_profit_price',
                  render: (v: number | null) =>
                    v != null ? <span className="num">{v}</span> : '-',
                },
              ]}
            />
          )}
        </PageSection>
      </div>

      <div style={{ marginTop: 'var(--sp-4)' }}>
        <PageSection
          title={`变量追踪 (${stock.thesis_variables?.length || 0})`}
          extra={
            <Button size="small" onClick={() => setThesisModalOpen(true)}>
              编辑
            </Button>
          }
        >
          {stock.thesis_variables && stock.thesis_variables.length > 0 ? (
            <Table
              size="small"
              rowKey={(v, i) => `${v.name}-${i}`}
              dataSource={stock.thesis_variables}
              pagination={false}
              columns={[
                { title: '变量名', dataIndex: 'name' },
                {
                  title: '当前值',
                  dataIndex: 'current_value',
                  render: (v: number | null) =>
                    v != null ? <span className="num">{v.toLocaleString()}</span> : '-',
                },
                {
                  title: '目标条件',
                  dataIndex: 'target_condition',
                  render: (v: string | null) => v || '-',
                },
                {
                  title: '单位',
                  dataIndex: 'unit',
                  render: (v: string | null) => v || '-',
                },
                {
                  title: '来源',
                  dataIndex: 'source',
                  render: (v: string, record) =>
                    v === 'lixinger' ? (
                      <Tag color="blue">
                        自动{record.synced_at ? ` (${record.synced_at})` : ''}
                      </Tag>
                    ) : (
                      <Tag>手动</Tag>
                    ),
                },
              ]}
            />
          ) : (
            <Empty description="暂无变量" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
        </PageSection>
      </div>

      <div style={{ marginTop: 'var(--sp-4)' }}>
        <Tabs
          defaultActiveKey="kline"
          items={[
            {
              key: 'kline',
              label: 'K线',
              children: <KlineChart stockCode={code} />,
            },
            {
              key: 'shareholders',
              label: `前十大股东 (${shareholders.length})`,
              children: shareholders.length ? (
                <Table
                  size="small"
                  rowKey={(r, i) => `${r.date}-${r.holder_name}-${i}`}
                  dataSource={shareholders}
                  columns={shareholderColumns}
                  pagination={{ pageSize: 20 }}
                />
              ) : (
                <Empty description="无股东数据" />
              ),
            },
            {
              key: 'north-flow',
              label: `北向资金 (${northFlow.length})`,
              children: northFlow.length ? (
                <Table
                  size="small"
                  rowKey="date"
                  dataSource={northFlow}
                  columns={northColumns}
                  pagination={{ pageSize: 20 }}
                />
              ) : (
                <Empty description="无北向资金数据（可能非互联互通标的）" />
              ),
            },
            {
              key: 'margin',
              label: `融资融券 (${margin.length})`,
              children: margin.length ? (
                <Table
                  size="small"
                  rowKey="date"
                  dataSource={margin}
                  columns={marginColumns}
                  pagination={{ pageSize: 20 }}
                />
              ) : (
                <Empty description="无融资融券数据" />
              ),
            },
            {
              key: 'revenue',
              label: `营收构成 (${revenue.length})`,
              children: revenue.length ? (
                <div>
                  {revenue.map((period) => (
                    <Card
                      key={period.date}
                      className="gojira-card"
                      bordered={false}
                      size="small"
                      title={`报告期 ${period.date}`}
                      style={{ marginBottom: 'var(--sp-3)' }}
                    >
                      <Table
                        size="small"
                        rowKey={(_, i) => `${period.date}-${i}`}
                        dataSource={period.segments}
                        pagination={false}
                        columns={[
                          { title: '业务/板块', dataIndex: 'name' },
                          { title: '类型', dataIndex: 'category' },
                          {
                            title: '营收',
                            dataIndex: 'revenue',
                            render: (v: number | null) =>
                              v != null ? <span className="num">{v.toLocaleString()}</span> : '-',
                          },
                          {
                            title: '占比',
                            dataIndex: 'ratio',
                            render: (v: number | null) =>
                              v != null ? (
                                <span className="num">{(v * 100).toFixed(2)}%</span>
                              ) : (
                                '-'
                              ),
                          },
                        ]}
                      />
                    </Card>
                  ))}
                </div>
              ) : (
                <Empty description="无营收构成数据" />
              ),
            },
          ]}
        />
      </div>

      <div style={{ marginTop: 'var(--sp-6)' }}>
        <Link to="/">
          <Text type="secondary">← 返回驾驶舱</Text>
        </Link>
      </div>

      <ThesisVariablesModal
        open={thesisModalOpen}
        code={code}
        initial={stock.thesis_variables || []}
        saving={thesisM.isPending}
        onCancel={() => setThesisModalOpen(false)}
        onSave={async (vars) => {
          await thesisM.mutateAsync(vars);
          setThesisModalOpen(false);
        }}
      />

      <QiuScorerWizard
        open={qiuModalOpen}
        code={code}
        initialValues={stock?.qiu_detail ?? undefined}
        onClose={() => setQiuModalOpen(false)}
        onSaved={async () => {
          await stockQ.refetch();
        }}
      />
    </div>
  );
}
