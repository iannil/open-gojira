import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Empty, Popconfirm, Space, Table, Tag, Typography, message } from 'antd';
import { ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';

import {
  listPendingCorpActions,
  processCorpAction,
  processPendingCorpActions,
} from '../api/client';
import type { CorpAction, CorpActionType } from '../api/types';

const { Text } = Typography;

const POLL_INTERVAL_MS = 60_000;

const actionTypeLabel: Record<CorpActionType, string> = {
  cash_dividend: '现金分红',
  stock_dividend: '送股',
  capitalization: '转增',
  rights_issue: '配股',
  delist: '退市',
  merger: '吸收合并',
  code_change: '换代码',
};

const actionColor: Record<CorpActionType, string> = {
  cash_dividend: 'green',
  stock_dividend: 'blue',
  capitalization: 'blue',
  rights_issue: 'orange',
  delist: 'red',
  merger: 'purple',
  code_change: 'cyan',
};

/**
 * Cockpit card: lists pending corp_actions (ex_date asc) with a one-click
 * "应用全部" button. Backed by the S4A.4 API endpoints.
 *
 * Rendered only when there are pending actions — collapses to nothing on
 * a clean backlog so the Cockpit stays calm.
 */
export function PendingCorpActionsCard() {
  const [pending, setPending] = useState<CorpAction[]>([]);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const list = await listPendingCorpActions(100);
      setPending(list);
    } catch {
      // silent — poll retries in 60s
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  const handleApplyAll = async () => {
    setApplying(true);
    try {
      const result = await processPendingCorpActions();
      message.success(`已应用 ${result.processed_count} 项公司行为`);
      await refresh();
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        '批量应用失败';
      message.error(detail);
    } finally {
      setApplying(false);
    }
  };

  const handleApplyOne = async (id: number) => {
    try {
      await processCorpAction(id);
      message.success('已应用');
      await refresh();
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        '应用失败';
      message.error(detail);
    }
  };

  if (pending.length === 0) {
    return null;
  }

  const columns = [
    {
      title: '代码',
      dataIndex: 'stock_code',
      width: 90,
    },
    {
      title: '类型',
      dataIndex: 'action_type',
      width: 100,
      render: (t: CorpActionType) => (
        <Tag color={actionColor[t]}>{actionTypeLabel[t] ?? t}</Tag>
      ),
    },
    {
      title: '除权日',
      dataIndex: 'ex_date',
      width: 110,
      render: (d: string) => dayjs(d).format('YYYY-MM-DD'),
    },
    {
      title: '参数',
      dataIndex: 'params_json',
      render: (p: Record<string, unknown>) => {
        const perShare = p.per_share as number | undefined;
        const per10 = p.per_10_shares as number | undefined;
        if (perShare) return `每股 ¥${perShare.toFixed(4)}`;
        if (per10) return `每 10 股 ${per10}`;
        return <Text type="secondary">{JSON.stringify(p)}</Text>;
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 90,
      render: (_: unknown, row: CorpAction) => (
        <Button size="small" onClick={() => handleApplyOne(row.id)}>
          应用
        </Button>
      ),
    },
  ];

  return (
    <Card
      size="small"
      title={
        <Space>
          <ThunderboltOutlined />
          <span>待处理公司行为</span>
          <Tag color="orange">{pending.length}</Tag>
        </Space>
      }
      extra={
        <Space>
          <Button
            size="small"
            icon={<ReloadOutlined />}
            onClick={refresh}
            loading={loading}
          >
            刷新
          </Button>
          <Popconfirm
            title={`确认批量应用全部 ${pending.length} 项?`}
            onConfirm={handleApplyAll}
            okText="确认"
            cancelText="取消"
          >
            <Button size="small" type="primary" loading={applying}>
              应用全部
            </Button>
          </Popconfirm>
        </Space>
      }
      style={{ marginBottom: 0 }}
    >
      {pending.length === 0 ? (
        <Empty description="暂无待处理项" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 8 }}
            message={`最近一项将于 ${dayjs(pending[0].ex_date).format('YYYY-MM-DD')} 生效`}
          />
          <Table
            rowKey="id"
            columns={columns}
            dataSource={pending}
            pagination={{ pageSize: 5, size: 'small' }}
            size="small"
          />
        </>
      )}
    </Card>
  );
}

export default PendingCorpActionsCard;
