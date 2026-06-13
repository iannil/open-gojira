import { useState } from 'react';
import { Button, Popconfirm, Space, Switch, Table, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { DeleteOutlined, EditOutlined, ExperimentOutlined, PlusOutlined } from '@ant-design/icons';

import QueryBoundary from '../../../components/QueryBoundary';
import { EmptyState } from '../../../components/primitives';
import { useNotificationChannelsQuery } from '../useMonitoringQueries';
import {
  useCreateChannelMutation,
  useDeleteChannelMutation,
  useTestChannelMutation,
  useUpdateChannelMutation,
} from '../useMonitoringMutations';
import type {
  NotificationChannel,
  NotificationChannelCreate,
  NotificationChannelType,
  NotificationChannelUpdate,
  NotificationSeverityFilter,
} from '../../../api/types';
import ChannelModal from './ChannelModal';

const { Text } = Typography;

const CHANNEL_TYPE_LABELS: Record<NotificationChannelType, string> = {
  in_app: '站内',
  server_chan: 'Server酱 (微信)',
  email: '邮件',
  dingtalk_webhook: '钉钉机器人',
  telegram_bot: 'Telegram Bot',
};

const SEVERITY_LABELS: Record<NotificationSeverityFilter, string> = {
  all: '全部 (info+)',
  warning_and_above: 'warning 及以上',
  critical_only: '仅 critical',
};

function summarizeConfig(config: Record<string, unknown>): string {
  const keys = Object.keys(config);
  if (keys.length === 0) return '—';
  return keys
    .map((k) => {
      const v = config[k];
      const display =
        typeof v === 'string' && v.length > 20 ? `${v.slice(0, 20)}…` : String(v);
      return `${k}: ${display}`;
    })
    .join('  ');
}

export default function ChannelsTab() {
  const channelsQ = useNotificationChannelsQuery();
  const createM = useCreateChannelMutation();
  const updateM = useUpdateChannelMutation();
  const deleteM = useDeleteChannelMutation();
  const testM = useTestChannelMutation();

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<NotificationChannel | null>(null);
  const [testingId, setTestingId] = useState<number | null>(null);

  const handleCreate = () => {
    setEditing(null);
    setModalOpen(true);
  };

  const handleEdit = (ch: NotificationChannel) => {
    setEditing(ch);
    setModalOpen(true);
  };

  const handleSave = async (payload: NotificationChannelCreate) => {
    if (editing) {
      const update: NotificationChannelUpdate = {
        config_json: payload.config_json,
        enabled: payload.enabled,
        severity_filter: payload.severity_filter,
      };
      await updateM.mutateAsync({ id: editing.id, payload: update });
    } else {
      await createM.mutateAsync(payload);
    }
    setModalOpen(false);
  };

  const handleTest = async (id: number) => {
    setTestingId(id);
    try {
      await testM.mutateAsync(id);
    } finally {
      setTestingId(null);
    }
  };

  const columns: ColumnsType<NotificationChannel> = [
    {
      title: '名称',
      dataIndex: 'name',
      width: 180,
      render: (v: string) => <code style={{ fontSize: 'var(--fs-sm)' }}>{v}</code>,
    },
    {
      title: '类型',
      dataIndex: 'type',
      width: 160,
      render: (v: NotificationChannelType) => CHANNEL_TYPE_LABELS[v] ?? v,
    },
    {
      title: '配置',
      dataIndex: 'config_json',
      ellipsis: true,
      render: (cfg: Record<string, unknown>) => (
        <Text type="secondary" style={{ fontSize: 'var(--fs-xs)' }}>
          {summarizeConfig(cfg)}
        </Text>
      ),
    },
    {
      title: '级别过滤',
      dataIndex: 'severity_filter',
      width: 130,
      render: (v: NotificationSeverityFilter) => <Tag>{SEVERITY_LABELS[v] ?? v}</Tag>,
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      width: 80,
      render: (enabled: boolean, record: NotificationChannel) => (
        <Switch
          size="small"
          checked={enabled}
          loading={updateM.isPending}
          onChange={(v) => updateM.mutate({ id: record.id, payload: { enabled: v } })}
        />
      ),
    },
    {
      title: '操作',
      width: 200,
      render: (_: unknown, record: NotificationChannel) => (
        <Space size="small">
          <Tooltip title="发送测试通知">
            <Button
              type="link"
              size="small"
              icon={<ExperimentOutlined />}
              loading={testingId === record.id}
              onClick={() => handleTest(record.id)}
            >
              测试
            </Button>
          </Tooltip>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          />
          <Popconfirm
            title={`确认删除 ${record.name}?`}
            onConfirm={() => deleteM.mutate(record.id)}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 'var(--sp-3)',
        }}
      >
        <Text type="secondary" style={{ fontSize: 'var(--fs-sm)' }}>
          配置系统告警的推送通道。盘中触发的止损/止盈、数据异常等告警将根据级别过滤分发到此处配置的通道。
        </Text>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
          新增通道
        </Button>
      </div>
      <QueryBoundary
        query={channelsQ}
        isEmpty={(d) => d.length === 0}
        emptyRender={
          <EmptyState
            variant="cold"
            title="还没有通知通道"
            description="配置 Server酱 / 邮件 / 钉钉 / Telegram 通道后，系统告警会自动推送。"
            cta={{ label: '新增通道', onClick: handleCreate }}
          />
        }
      >
        {(data) => (
          <Table<NotificationChannel>
            rowKey="id"
            columns={columns}
            dataSource={data}
            loading={channelsQ.isFetching && !channelsQ.data}
            pagination={false}
            size="middle"
          />
        )}
      </QueryBoundary>
      <ChannelModal
        open={modalOpen}
        initial={editing}
        onCancel={() => setModalOpen(false)}
        onSave={handleSave}
      />
    </div>
  );
}
