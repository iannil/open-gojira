import { useState } from 'react';
import { Button, Popconfirm, Select, Table, Tag, Input, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined } from '@ant-design/icons';
import { useQueryClient } from '@tanstack/react-query';

import { PageHeader, FilterBar, EmptyState, StatCard } from '../../components/primitives';
import QueryBoundary from '../../components/QueryBoundary';
import { defaultPagination } from '../../lib/pagination';
import TradeEntryModal from '../../components/TradeEntryModal';
import { CashAdjustmentModal } from '../../components/CashAdjustmentModal';
import { useTradesQuery, useCashBalanceQuery } from './useTradeQueries';
import { useReverseTradeMutation } from './useTradeMutations';
import { cashKeys, tradeKeys, type TradeListFilter } from './queries';
import type { Trade, TradeSide } from '../../api/types';

const { Text } = Typography;

const SIDE_COLOR: Record<TradeSide, string> = {
  BUY: 'green',
  SELL: 'red',
  DIVIDEND: 'blue',
  CORP_ACTION: 'purple',
};

const SIDE_LABEL: Record<TradeSide, string> = {
  BUY: '买入',
  SELL: '卖出',
  DIVIDEND: '分红',
  CORP_ACTION: '公司行为',
};

function formatCurrency(v: number): string {
  return `¥${v.toFixed(2)}`;
}

function formatDateTime(s: string): string {
  return new Date(s).toLocaleString('zh-CN', { hour12: false });
}

export default function TradesPage() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [cashModalMode, setCashModalMode] = useState<'deposit' | 'withdrawal'>('deposit');
  const [cashModalOpen, setCashModalOpen] = useState(false);
  const [filter, setFilter] = useState<TradeListFilter>({ limit: 100 });

  const tradesQ = useTradesQuery(filter);
  const balanceQ = useCashBalanceQuery();
  const reverseM = useReverseTradeMutation();

  const trades = tradesQ.data?.items ?? [];
  const total = tradesQ.data?.total ?? 0;
  const balance = balanceQ.data ?? null;

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: tradeKeys.all() });
    queryClient.invalidateQueries({ queryKey: cashKeys.all() });
    queryClient.invalidateQueries({ queryKey: ['cockpit'] });
    queryClient.invalidateQueries({ queryKey: ['holdings'] });
  };

  const handleResetFilter = () => setFilter({ limit: 100 });

  const columns: ColumnsType<Trade> = [
    { title: 'ID', dataIndex: 'id', width: 60, render: (v: number) => <span className="num">{v}</span> },
    {
      title: '代码',
      dataIndex: 'stock_code',
      width: 90,
      render: (v: string) => <Text code>{v}</Text>,
    },
    {
      title: '方向',
      dataIndex: 'side',
      width: 90,
      render: (s: TradeSide) => <Tag color={SIDE_COLOR[s]}>{SIDE_LABEL[s]}</Tag>,
    },
    {
      title: '价格',
      dataIndex: 'price',
      width: 90,
      align: 'right',
      render: (v: number) => <span className="num">{formatCurrency(v)}</span>,
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      width: 100,
      align: 'right',
      render: (q: number) => <span className="num">{Math.abs(q).toLocaleString('zh-CN')}</span>,
    },
    {
      title: '成交时间',
      dataIndex: 'filled_at',
      width: 160,
      render: (s: string) => (
        <span
          className="num"
          style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}
        >
          {formatDateTime(s)}
        </span>
      ),
    },
    {
      title: '成交额',
      dataIndex: 'total_value',
      width: 120,
      align: 'right',
      render: (v: number) => <span className="num">{formatCurrency(v)}</span>,
    },
    {
      title: '费用',
      width: 110,
      align: 'right',
      render: (_, r) => (
        <span className="num">
          {formatCurrency(r.commission + r.stamp_duty + r.transfer_fee)}
        </span>
      ),
    },
    {
      title: '来源',
      dataIndex: 'source',
      width: 100,
      render: (s: string) => <Tag>{s}</Tag>,
    },
    {
      title: '操作',
      width: 110,
      fixed: 'right',
      render: (_, r) =>
        r.reversed_by_trade_id !== null || r.source === 'reversal' ? (
          <Tag color="default">已红冲</Tag>
        ) : (
          <Popconfirm
            title={`确认红冲 Trade #${r.id}?`}
            description="将生成反向 trade，现金账户同步回滚"
            okText="确认"
            cancelText="取消"
            onConfirm={() => reverseM.mutate(r.id)}
          >
            <Button size="small" danger loading={reverseM.isPending}>
              红冲
            </Button>
          </Popconfirm>
        ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="成交流水"
        enLabel="Trades"
        purpose="记录每一笔实际成交（买入 / 卖出 / 分红 / 公司行为），现金账户自动联动。红冲生成反向 trade 回滚。"
        flow={[
          { to: '/plans', label: '预案' },
          { to: '/candidates', label: '候选池' },
          { label: '成交流水' },
          { to: '/review', label: '复盘' },
        ]}
        actions={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
            录入成交
          </Button>
        }
      />

      <div style={{ marginBottom: 'var(--sp-4)' }}>
        <StatCard
          label="现金余额"
          value={balance ? formatCurrency(balance.balance) : '—'}
          hint={
            balance
              ? `更新于 ${formatDateTime(balance.as_of_at)}`
              : '尚未初始化现金账户'
          }
          loading={balanceQ.isLoading}
        />
      </div>

      <FilterBar
        onReset={handleResetFilter}
        actions={
          <>
            <Button
              onClick={() => {
                setCashModalMode('deposit');
                setCashModalOpen(true);
              }}
            >
              入金
            </Button>
            <Button
              danger
              onClick={() => {
                setCashModalMode('withdrawal');
                setCashModalOpen(true);
              }}
            >
              取现
            </Button>
          </>
        }
      >
        <Input.Search
          placeholder="按代码过滤"
          allowClear
          onSearch={(v) => setFilter((f) => ({ ...f, code: v.trim() || undefined }))}
          style={{ width: 200 }}
        />
        <Select
          placeholder="按方向过滤"
          allowClear
          onChange={(v) => setFilter((f) => ({ ...f, side: v }))}
          style={{ width: 140 }}
          options={[
            { value: 'BUY', label: '买入' },
            { value: 'SELL', label: '卖出' },
            { value: 'DIVIDEND', label: '分红' },
            { value: 'CORP_ACTION', label: '公司行为' },
          ]}
        />
      </FilterBar>

      <QueryBoundary
        query={tradesQ}
        isEmpty={(data) => data.items.length === 0}
        emptyRender={
          <EmptyState
            variant={filter.code || filter.side ? 'filter' : 'cold'}
            title={filter.code || filter.side ? '无匹配的成交' : '还没有任何成交'}
            description={
              filter.code || filter.side
                ? undefined
                : '录入第一笔买入成交，或从候选池选股后录入。'
            }
            cta={
              filter.code || filter.side
                ? undefined
                : { label: '录入第一笔成交', onClick: () => setModalOpen(true) }
            }
            onClearFilter={
              filter.code || filter.side ? handleResetFilter : undefined
            }
          />
        }
      >
        {() => (
          <Table
            columns={columns}
            dataSource={trades}
            rowKey="id"
            loading={tradesQ.isFetching && !tradesQ.data}
            size="small"
            pagination={{ ...defaultPagination, total, defaultPageSize: 100 }}
            scroll={{ x: 1200 }}
          />
        )}
      </QueryBoundary>

      <TradeEntryModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onCreated={invalidateAll}
      />
      <CashAdjustmentModal
        open={cashModalOpen}
        mode={cashModalMode}
        onClose={() => setCashModalOpen(false)}
        onCreated={invalidateAll}
      />
    </div>
  );
}
