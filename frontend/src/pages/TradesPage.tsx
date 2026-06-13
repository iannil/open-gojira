import { useEffect, useState, useCallback } from 'react';
import {
  Table,
  Button,
  Space,
  Tag,
  Input,
  Select,
  Popconfirm,
  Typography,
  Card,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { TransactionOutlined } from '@ant-design/icons';
import PageHeader from '../components/PageHeader';
import TradeEntryModal from '../components/TradeEntryModal';
import { CashAdjustmentModal } from '../components/CashAdjustmentModal';
import { useAntdStatic } from '../hooks/useAntdStatic';
import { listTrades, reverseTrade, getCashBalance } from '../api/client';
import type { Trade, TradeSide, CashBalance } from '../api/types';

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

interface Filter {
  code?: string;
  side?: string;
}

function formatCurrency(v: number): string {
  return `¥${v.toFixed(2)}`;
}

function formatDateTime(s: string): string {
  return new Date(s).toLocaleString('zh-CN', { hour12: false });
}

export default function TradesPage() {
  const { message } = useAntdStatic();
  const [trades, setTrades] = useState<Trade[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [balance, setBalance] = useState<CashBalance | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [cashModalMode, setCashModalMode] = useState<'deposit' | 'withdrawal'>('deposit');
  const [cashModalOpen, setCashModalOpen] = useState(false);
  const [filter, setFilter] = useState<Filter>({});

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [resp, bal] = await Promise.all([
        listTrades({ ...filter, limit: 100 }),
        getCashBalance(),
      ]);
      setTrades(resp.items);
      setTotal(resp.total);
      setBalance(bal);
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail;
      message.error(detail || '加载失败');
    } finally {
      setLoading(false);
    }
  }, [filter, message]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const handleReverse = async (id: number) => {
    try {
      await reverseTrade(id);
      message.success('已红冲');
      await fetchData();
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail;
      message.error(detail || '红冲失败');
    }
  };

  const columns: ColumnsType<Trade> = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '代码', dataIndex: 'stock_code', width: 90 },
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
      render: (v: number) => formatCurrency(v),
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      width: 100,
      align: 'right',
      render: (q: number) => Math.abs(q).toLocaleString('zh-CN'),
    },
    {
      title: '成交时间',
      dataIndex: 'filled_at',
      width: 160,
      render: (s: string) => formatDateTime(s),
    },
    {
      title: '成交额',
      dataIndex: 'total_value',
      width: 120,
      align: 'right',
      render: (v: number) => formatCurrency(v),
    },
    {
      title: '费用',
      width: 110,
      align: 'right',
      render: (_, r) => formatCurrency(r.commission + r.stamp_duty + r.transfer_fee),
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
            description="将生成反向 trade,现金账户同步回滚"
            okText="确认"
            cancelText="取消"
            onConfirm={() => handleReverse(r.id)}
          >
            <Button size="small" danger>
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
        icon={<TransactionOutlined />}
        description="手动录入成交、查看红冲流水,现金余额自动联动。"
      />

      <Card size="small" style={{ marginBottom: 16 }}>
        <Space size="large" align="baseline">
          <Text type="secondary">现金余额:</Text>
          <Text strong style={{ fontSize: 20 }}>
            {balance ? formatCurrency(balance.balance) : '—'}
          </Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            (更新于 {balance ? formatDateTime(balance.as_of_at) : '—'})
          </Text>
        </Space>
      </Card>

      <Card>
        <Space style={{ marginBottom: 16 }} wrap>
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
          <Button type="primary" onClick={() => setModalOpen(true)}>
            录入成交
          </Button>
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
        </Space>
        <Table
          columns={columns}
          dataSource={trades}
          rowKey="id"
          loading={loading}
          size="small"
          pagination={{ total, pageSize: 100, showSizeChanger: false }}
          scroll={{ x: 1200 }}
        />
      </Card>

      <TradeEntryModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onCreated={() => void fetchData()}
      />
      <CashAdjustmentModal
        open={cashModalOpen}
        mode={cashModalMode}
        onClose={() => setCashModalOpen(false)}
        onCreated={() => void fetchData()}
      />
    </div>
  );
}
