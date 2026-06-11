/**
 * Stock detail — read-only drill-in from Cockpit / Plans / Drafts.
 *
 * Trimmed in Step 4: removed legacy "买入纪律" (PreTradeChecklist) and the
 * navigation buttons to deleted pages. Realtime PE/PB/DYR now come from
 * the valuation-percentile endpoint instead of the legacy dashboard.
 */

import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Input,
  InputNumber,
  Modal,
  Space,
  Spin,
  Statistic,
  Table,
  Tabs,
  Tag,
} from 'antd';

import {
  bulkAddWatchlistItems,
  fetchMarginTrading,
  fetchNorthFlow,
  fetchRevenueComposition,
  fetchShareholders,
  fetchThesisTemplates,
  listCandidates,
  getStock,
  listHoldings,
  listWatchlistGroups,
  updateThesisVariables,
} from '../api/client';
import { useAntdStatic } from '../hooks/useAntdStatic';
import KlineChart from '../components/stock/KlineChart';
import PageHeader from '../components/PageHeader';
import QiuScorerWizard from '../components/QiuScorerWizard';
import type { RevenueComposition, ThesisVariable } from '../api/types';
import type {
  HoldingResponse,
  MarginTradingRecord,
  NorthFlowRecord,
  ShareholderRecord,
  StockResponse,
  WatchlistGroupResponse,
  CandidateResponse,
} from '../api/types';

// Candidate status labels used in stock detail view

export default function StockDetailPage() {
  const { message } = useAntdStatic();
  const { code = '' } = useParams<{ code: string }>();
  const [stock, setStock] = useState<StockResponse | null>(null);
  const [candidates, setCandidates] = useState<CandidateResponse[]>([]);
  const [holdings, setHoldings] = useState<HoldingResponse[]>([]);
  const [shareholders, setShareholders] = useState<ShareholderRecord[]>([]);
  const [northFlow, setNorthFlow] = useState<NorthFlowRecord[]>([]);
  const [margin, setMargin] = useState<MarginTradingRecord[]>([]);
  const [dataErrors, setDataErrors] = useState<string[]>([]);
  const [groups, setGroups] = useState<WatchlistGroupResponse[]>([]);
  const [revenue, setRevenue] = useState<RevenueComposition[]>([]);
  const [loading, setLoading] = useState(true);
  const [thesisModalOpen, setThesisModalOpen] = useState(false);
  const [thesisVariables, setThesisVariables] = useState<ThesisVariable[]>([]);
  const [savingThesis, setSavingThesis] = useState(false);
  const [qiuModalOpen, setQiuModalOpen] = useState(false);

  useEffect(() => {
    if (!code) return;
    setLoading(true);
    Promise.allSettled([
      getStock(code),
      listCandidates({ status: 'active' }).then(cs => cs.filter(c => c.stock_code === code)),
      listHoldings().then((all) =>
        all.filter((h) => h.stock_code === code && !h.sell_date),
      ),
      fetchShareholders(code),
      fetchNorthFlow(code),
      fetchMarginTrading(code),
      listWatchlistGroups(),
      fetchRevenueComposition(code),
    ]).then(([s, cs, h, sh, nf, mg, gs, rv]) => {
      const errs: string[] = [];
      if (s.status === 'fulfilled') {
        setStock(s.value);
        setThesisVariables(s.value.thesis_variables || []);
      }
      if (cs.status === 'fulfilled') setCandidates(cs.value);
      if (h.status === 'fulfilled') setHoldings(h.value);
      if (sh.status === 'fulfilled') setShareholders(sh.value);
      else errs.push('十大股东');
      if (nf.status === 'fulfilled') setNorthFlow(nf.value);
      else errs.push('北向资金');
      if (mg.status === 'fulfilled') setMargin(mg.value);
      else errs.push('融资融券');
      if (gs.status === 'fulfilled') setGroups(gs.value);
      if (rv.status === 'fulfilled') setRevenue(rv.value);
      setDataErrors(errs);
      setLoading(false);
    });
  }, [code]);

  const handleAddToWatchlist = async () => {
    if (!groups.length) {
      message.info('暂无关注分组');
      return;
    }
    const target = groups[0];
    await bulkAddWatchlistItems(target.id, [code]);
    message.success(`已加入分组 "${target.name}"`);
  };

  const handleEditThesisVariables = () => {
    setThesisVariables(stock?.thesis_variables || []);
    setThesisModalOpen(true);
  };

  const handleAddThesisVariable = () => {
    setThesisVariables([
      ...thesisVariables,
      {
        name: '',
        current_value: null,
        target_condition: null,
        unit: null,
        source: '',
      },
    ]);
  };

  const handleRemoveThesisVariable = (index: number) => {
    setThesisVariables(thesisVariables.filter((_, i) => i !== index));
  };

  const handleThesisVariableChange = (
    index: number,
    field: keyof ThesisVariable,
    value: string | number | null,
  ) => {
    const updated = [...thesisVariables];
    updated[index] = { ...updated[index], [field]: value };
    setThesisVariables(updated);
  };

  const handleSaveThesisVariables = async () => {
    const valid = thesisVariables.every(
      (v) => v.name && v.source,
    );
    if (!valid) {
      message.error('请填写完整的变量名称和数据来源');
      return;
    }
    setSavingThesis(true);
    try {
      await updateThesisVariables(code, thesisVariables);
      message.success('变量已更新');
      setThesisModalOpen(false);
      // Reload stock data
      const updatedStock = await getStock(code);
      setStock(updatedStock);
      setThesisVariables(updatedStock.thesis_variables || []);
    } catch (e) {
      message.error(`保存失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSavingThesis(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: 48, textAlign: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!stock) {
    return <Empty description={`未找到股票 ${code}`} />;
  }

  const shareholderColumns = [
    { title: '日期', dataIndex: 'date' },
    { title: '股东', dataIndex: 'holder_name' },
    { title: '类型', dataIndex: 'holder_type' },
    {
      title: '持股数量',
      dataIndex: 'holding_quantity',
      render: (v: number | null) => (v != null ? v.toLocaleString() : '-'),
    },
    {
      title: '持股比例',
      dataIndex: 'holding_ratio',
      render: (v: number | null) =>
        v != null ? `${(v * 100).toFixed(2)}%` : '-',
    },
  ];

  const northColumns = [
    { title: '日期', dataIndex: 'date' },
    {
      title: '净买入',
      dataIndex: 'net_buy_amount',
      render: (v: number | null) => (v != null ? v.toLocaleString() : '-'),
    },
    {
      title: '持股数量',
      dataIndex: 'holding_quantity',
      render: (v: number | null) => (v != null ? v.toLocaleString() : '-'),
    },
    {
      title: '持股比例',
      dataIndex: 'holding_ratio',
      render: (v: number | null) =>
        v != null ? `${(v * 100).toFixed(2)}%` : '-',
    },
  ];

  const marginColumns = [
    { title: '日期', dataIndex: 'date' },
    {
      title: '融资余额',
      dataIndex: 'financing_balance',
      render: (v: number | null) => (v != null ? v.toLocaleString() : '-'),
    },
    {
      title: '融券余额',
      dataIndex: 'securities_balance',
      render: (v: number | null) => (v != null ? v.toLocaleString() : '-'),
    },
    {
      title: '净融资',
      dataIndex: 'net_financing',
      render: (v: number | null) => (v != null ? v.toLocaleString() : '-'),
    },
  ];

  return (
    <div>
      <PageHeader title={<><code style={{ marginRight: 12 }}>{stock.code}</code>{stock.name}</>} />
      <Space style={{ marginTop: 8 }} wrap>
          {stock.industry && <Tag>{stock.industry}</Tag>}
          {stock.tier && (
            <Tag color={stock.tier === 'core' ? '#B8860B' : '#6A5ACD'}>
              {stock.tier === 'core' ? '核心' : '关注'}
            </Tag>
          )}
          {stock.listed_date && <Tag>上市 {stock.listed_date}</Tag>}
          {candidates.length > 0 && (
            <Tag color="green">
              候选: {candidates.map(c => c.plan_name).join(', ')}
            </Tag>
          )}
        </Space>
        <Space style={{ marginTop: 12 }}>
          <Button onClick={handleAddToWatchlist}>加入自选</Button>
          <Button onClick={() => setQiuModalOpen(true)}>
            求评分 ({stock.qiu_score ?? 0}/3)
          </Button>
          <Button onClick={handleEditThesisVariables}>编辑变量</Button>
          <Link to="/plans">
            <Button type="primary">管理预案</Button>
          </Link>
        </Space>

      {dataErrors.length > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message={`部分数据加载失败：${dataErrors.join('、')}`}
        />
      )}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 16,
          marginBottom: 16,
        }}
      >
        <Card>
          <Statistic title="代码" value={stock.code} />
        </Card>
        <Card>
          <Statistic title="行业" value={stock.industry ?? '-'} />
        </Card>
        <Card>
          <Statistic title="持仓数量" value={holdings.length} />
        </Card>
        <Card>
          <Statistic title="候选预案" value={candidates.length > 0 ? candidates.map(c => c.plan_name).join(', ') : '无'} />
        </Card>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(2, 1fr)',
          gap: 16,
          marginBottom: 16,
        }}
      >
        <Card title="基本信息">
          <Descriptions column={1} size="small">
            <Descriptions.Item label="代码">{stock.code}</Descriptions.Item>
            <Descriptions.Item label="名称">{stock.name}</Descriptions.Item>
            <Descriptions.Item label="行业">
              {stock.industry ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label="上市日">
              {stock.listed_date ?? '-'}
            </Descriptions.Item>
          </Descriptions>
        </Card>
        <Card title={`当前持仓 (${holdings.length})`}>
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
                { title: '买入价', dataIndex: 'buy_price' },
                { title: '数量', dataIndex: 'quantity' },
                { title: '止盈价', dataIndex: 'stop_profit_price' },
              ]}
            />
          )}
        </Card>
      </div>

      <Card
        title={`变量追踪 (${stock.thesis_variables?.length || 0})`}
        style={{ marginBottom: 16 }}
        extra={
          <Button size="small" onClick={handleEditThesisVariables}>
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
                  v != null ? v.toLocaleString() : '-',
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
                render: (v: string, record: ThesisVariable) =>
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
          <Empty
            description="暂无变量"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        )}
      </Card>

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
                    size="small"
                    title={`报告期 ${period.date}`}
                    style={{ marginBottom: 12 }}
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
                            v != null ? v.toLocaleString() : '-',
                        },
                        {
                          title: '占比',
                          dataIndex: 'ratio',
                          render: (v: number | null) =>
                            v != null
                              ? `${(v * 100).toFixed(2)}%`
                              : '-',
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

      <div style={{ marginTop: 24 }}>
        <Link to="/">← 返回驾驶舱</Link>
      </div>

      <Modal
        open={thesisModalOpen}
        title="编辑变量"
        okText="保存"
        cancelText="取消"
        onCancel={() => setThesisModalOpen(false)}
        onOk={handleSaveThesisVariables}
        confirmLoading={savingThesis}
        width={800}
        destroyOnHidden
      >
        <div style={{ marginBottom: 16 }}>
          <Space>
            <Button size="small" onClick={handleAddThesisVariable}>
              添加变量
            </Button>
            <Button
              size="small"
              onClick={async () => {
                try {
                  const res = await fetchThesisTemplates(code);
                  if (res.templates.length === 0) {
                    message.info(`行业 "${res.industry}" 暂无模板`);
                    return;
                  }
                  const newVars: ThesisVariable[] = res.templates.map((t) => ({
                    name: t.name,
                    current_value: null,
                    target_condition: null,
                    unit: t.unit,
                    source: t.source,
                  }));
                  setThesisVariables([...thesisVariables, ...newVars]);
                  message.success(`已加载 ${newVars.length} 个模板变量`);
                } catch {
                  message.error('加载模板失败');
                }
              }}
            >
              从行业模板加载
            </Button>
          </Space>
        </div>
        {thesisVariables.length === 0 ? (
          <Empty
            description="暂无变量，点击上方按钮添加"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <Space orientation="vertical" style={{ width: '100%' }} size={16}>
            {thesisVariables.map((variable, index) => (
              <Card
                key={index}
                size="small"
                title={`变量 ${index + 1}`}
                extra={
                  <Button
                    size="small"
                    danger
                    onClick={() => handleRemoveThesisVariable(index)}
                  >
                    删除
                  </Button>
                }
              >
                <Space orientation="vertical" style={{ width: '100%' }} size={8}>
                  <Input
                    placeholder="变量名称（如：不良贷款率）"
                    value={variable.name}
                    onChange={(e) =>
                      handleThesisVariableChange(index, 'name', e.target.value)
                    }
                  />
                  <Space.Compact style={{ width: '100%' }}>
                    <InputNumber
                      placeholder="当前值"
                      value={variable.current_value}
                      onChange={(v) =>
                        handleThesisVariableChange(index, 'current_value', v)
                      }
                      style={{ width: '50%' }}
                    />
                    <Input
                      placeholder="单位（如：% / 亿元）"
                      value={variable.unit || ''}
                      onChange={(e) =>
                        handleThesisVariableChange(index, 'unit', e.target.value)
                      }
                      style={{ width: '50%' }}
                    />
                  </Space.Compact>
                  <Input
                    placeholder="目标条件（如：< 3% / 稳定）"
                    value={variable.target_condition || ''}
                    onChange={(e) =>
                      handleThesisVariableChange(
                        index,
                        'target_condition',
                        e.target.value,
                      )
                    }
                  />
                  <Input
                    placeholder="数据来源（如：年报 / 理杏仁 / 同花顺）"
                    value={variable.source ?? ''}
                    onChange={(e) =>
                      handleThesisVariableChange(index, 'source', e.target.value)
                    }
                  />
                </Space>
              </Card>
            ))}
          </Space>
        )}
      </Modal>

      <QiuScorerWizard
        open={qiuModalOpen}
        code={code}
        initialValues={stock?.qiu_detail ?? undefined}
        onClose={() => setQiuModalOpen(false)}
        onSaved={async () => {
          const updated = await getStock(code);
          setStock(updated);
        }}
      />
    </div>
  );
}
