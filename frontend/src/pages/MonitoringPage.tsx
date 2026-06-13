import { useCallback, useEffect, useState } from 'react';
import {
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  BellOutlined,
  DeleteOutlined,
  EditOutlined,
  ExperimentOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';

import PageHeader from '../components/PageHeader';
import { useAntdStatic } from '../hooks/useAntdStatic';
import {
  createNotificationChannel,
  createRiskRule,
  deleteNotificationChannel,
  deleteRiskRule,
  listNotificationChannels,
  listRiskRules,
  testNotificationChannel,
  updateNotificationChannel,
  updateRiskRule,
} from '../api/client';
import type {
  HoldingRiskRule,
  NotificationChannel,
  NotificationChannelCreate,
  NotificationChannelType,
  NotificationSeverityFilter,
  RiskRuleCreate,
  StopLossType,
  TakeProfitType,
} from '../api/types';

const { Text } = Typography;

// ── Constants ──────────────────────────────────────────────────────────

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

const STOP_LOSS_TYPE_LABELS: Record<StopLossType, string> = {
  pct_from_cost: '成本百分比',
  trailing: '追踪止损',
  fixed_price: '固定价格',
};

// ── Helpers ────────────────────────────────────────────────────────────

function formatPct(fraction: number | null | undefined, digits = 1): string {
  if (fraction == null || !Number.isFinite(fraction)) return '—';
  return `${(fraction * 100).toFixed(digits)}%`;
}

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

// ── Channel Modal ──────────────────────────────────────────────────────

interface ChannelFormValues {
  name: string;
  type: NotificationChannelType;
  config_text: string;
  enabled: boolean;
  severity_filter: NotificationSeverityFilter;
}

function ChannelModal({
  open,
  initial,
  onCancel,
  onSave,
}: {
  open: boolean;
  initial: NotificationChannel | null;
  onCancel: () => void;
  onSave: (payload: NotificationChannelCreate) => Promise<void>;
}) {
  const { message } = useAntdStatic();
  const [form] = Form.useForm<ChannelFormValues>();
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      form.setFieldsValue({
        name: initial?.name ?? '',
        type: initial?.type ?? 'server_chan',
        config_text: initial ? JSON.stringify(initial.config_json, null, 2) : '{}',
        enabled: initial?.enabled ?? true,
        severity_filter: initial?.severity_filter ?? 'all',
      });
    }
  }, [open, initial, form]);

  const handleSave = async () => {
    let values: ChannelFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    let config_json: Record<string, unknown>;
    try {
      config_json = JSON.parse(values.config_text || '{}');
    } catch {
      message.error('config_json 格式错误，必须是合法 JSON');
      return;
    }
    setSubmitting(true);
    try {
      await onSave({
        name: values.name,
        type: values.type,
        config_json,
        enabled: values.enabled,
        severity_filter: values.severity_filter,
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={initial ? '编辑通知通道' : '新增通知通道'}
      open={open}
      onCancel={onCancel}
      onOk={handleSave}
      okText="保存"
      cancelText="取消"
      confirmLoading={submitting}
      width={560}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="name"
          label="名称"
          rules={[{ required: true, message: '请输入通道名称' }]}
        >
          <Input placeholder="如 wechat_main" disabled={!!initial} />
        </Form.Item>
        <Form.Item
          name="type"
          label="类型"
          rules={[{ required: true }]}
        >
          <Select
            options={Object.entries(CHANNEL_TYPE_LABELS).map(([v, label]) => ({
              value: v,
              label,
            }))}
            disabled={!!initial}
          />
        </Form.Item>
        <Form.Item
          name="config_text"
          label="配置 (JSON)"
          tooltip="server_chan: {sendkey}; email: {to, smtp_host, smtp_user, smtp_pass}; dingtalk_webhook: {webhook_url}; telegram_bot: {bot_token, chat_id}"
          rules={[{ required: true }]}
        >
          <Input.TextArea rows={4} style={{ fontFamily: 'monospace' }} />
        </Form.Item>
        <Form.Item name="severity_filter" label="告警级别过滤">
          <Select
            options={Object.entries(SEVERITY_LABELS).map(([v, label]) => ({
              value: v,
              label,
            }))}
          />
        </Form.Item>
        <Form.Item name="enabled" label="启用" valuePropName="checked">
          <Switch />
        </Form.Item>
      </Form>
    </Modal>
  );
}

// ── Channels Tab ───────────────────────────────────────────────────────

function ChannelsTab() {
  const { message } = useAntdStatic();
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<NotificationChannel | null>(null);
  const [testing, setTesting] = useState<number | null>(null);

  const fetchChannels = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listNotificationChannels();
      setChannels(data);
    } catch {
      message.error('获取通知通道列表失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    fetchChannels();
  }, [fetchChannels]);

  const handleCreate = () => {
    setEditing(null);
    setModalOpen(true);
  };

  const handleEdit = (ch: NotificationChannel) => {
    setEditing(ch);
    setModalOpen(true);
  };

  const handleSave = async (payload: NotificationChannelCreate) => {
    try {
      if (editing) {
        await updateNotificationChannel(editing.id, {
          config_json: payload.config_json,
          enabled: payload.enabled,
          severity_filter: payload.severity_filter,
        });
        message.success('已更新');
      } else {
        await createNotificationChannel(payload);
        message.success('已新增');
      }
      setModalOpen(false);
      fetchChannels();
    } catch {
      message.error('保存失败');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteNotificationChannel(id);
      message.success('已删除');
      fetchChannels();
    } catch {
      message.error('删除失败');
    }
  };

  const handleToggle = async (ch: NotificationChannel, enabled: boolean) => {
    try {
      await updateNotificationChannel(ch.id, { enabled });
      message.success(enabled ? '已启用' : '已停用');
      fetchChannels();
    } catch {
      message.error('更新失败');
    }
  };

  const handleTest = async (id: number) => {
    setTesting(id);
    try {
      const result = await testNotificationChannel(id);
      if (result.success) {
        message.success('测试通知已发送');
      } else {
        message.warning(`发送失败：${result.error ?? '未知错误'}`);
      }
    } catch {
      message.error('测试请求失败');
    } finally {
      setTesting(null);
    }
  };

  const columns: ColumnsType<NotificationChannel> = [
    {
      title: '名称',
      dataIndex: 'name',
      width: 180,
      render: (v: string) => <code style={{ fontSize: 13 }}>{v}</code>,
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
        <Text type="secondary" style={{ fontSize: 12 }}>
          {summarizeConfig(cfg)}
        </Text>
      ),
    },
    {
      title: '级别过滤',
      dataIndex: 'severity_filter',
      width: 130,
      render: (v: NotificationSeverityFilter) => (
        <Tag>{SEVERITY_LABELS[v] ?? v}</Tag>
      ),
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      width: 80,
      render: (enabled: boolean, record: NotificationChannel) => (
        <Switch
          size="small"
          checked={enabled}
          onChange={(v) => handleToggle(record, v)}
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
              loading={testing === record.id}
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
            onConfirm={() => handleDelete(record.id)}
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
          marginBottom: 12,
        }}
      >
        <Text type="secondary">
          配置系统告警的推送通道。盘中触发的止损/止盈、数据异常等告警将根据级别过滤分发到此处配置的通道。
        </Text>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
          新增通道
        </Button>
      </div>
      <Table<NotificationChannel>
        rowKey="id"
        columns={columns}
        dataSource={channels}
        loading={loading}
        pagination={false}
        size="middle"
      />
      <ChannelModal
        open={modalOpen}
        initial={editing}
        onCancel={() => setModalOpen(false)}
        onSave={handleSave}
      />
    </div>
  );
}

// ── Risk Rules Modal ───────────────────────────────────────────────────

interface RiskRuleFormValues {
  stock_code: string;
  stop_loss_pct: number | null;
  stop_loss_type: StopLossType;
  take_profit_pct: number | null;
  take_profit_type: TakeProfitType;
  peak_price: number | null;
  enabled: boolean;
}

function RiskRuleModal({
  open,
  initial,
  onCancel,
  onSave,
}: {
  open: boolean;
  initial: HoldingRiskRule | null;
  onCancel: () => void;
  onSave: (
    payload: RiskRuleCreate & { peak_price?: number | null },
  ) => Promise<void>;
}) {
  const [form] = Form.useForm<RiskRuleFormValues>();
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      form.setFieldsValue({
        stock_code: initial?.stock_code ?? '',
        stop_loss_pct: initial?.stop_loss_pct ?? null,
        stop_loss_type: initial?.stop_loss_type ?? 'pct_from_cost',
        take_profit_pct: initial?.take_profit_pct ?? null,
        take_profit_type: initial?.take_profit_type ?? 'pct_from_cost',
        peak_price: initial?.peak_price ?? null,
        enabled: initial?.enabled ?? true,
      });
    }
  }, [open, initial, form]);

  const handleSave = async () => {
    let values: RiskRuleFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    setSubmitting(true);
    try {
      await onSave({
        stock_code: values.stock_code,
        stop_loss_pct: values.stop_loss_pct,
        stop_loss_type: values.stop_loss_type,
        take_profit_pct: values.take_profit_pct,
        take_profit_type: values.take_profit_type,
        peak_price: values.peak_price,
        enabled: values.enabled,
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={initial ? `编辑规则 (${initial.stock_code})` : '新增止损止盈规则'}
      open={open}
      onCancel={onCancel}
      onOk={handleSave}
      okText="保存"
      cancelText="取消"
      confirmLoading={submitting}
      width={520}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="stock_code"
          label="股票代码"
          rules={[{ required: true, message: '请输入股票代码' }]}
        >
          <Input placeholder="如 600519" disabled={!!initial} />
        </Form.Item>
        <Space style={{ display: 'flex' }} size="middle">
          <Form.Item name="stop_loss_pct" label="止损阈值 (小数)" style={{ flex: 1 }}>
            <InputNumber
              style={{ width: '100%' }}
              step={0.01}
              min={0}
              max={1}
              placeholder="0.08 = -8%"
            />
          </Form.Item>
          <Form.Item name="stop_loss_type" label="止损类型" style={{ flex: 1 }}>
            <Select
              options={Object.entries(STOP_LOSS_TYPE_LABELS).map(([v, label]) => ({
                value: v,
                label,
              }))}
            />
          </Form.Item>
        </Space>
        <Space style={{ display: 'flex' }} size="middle">
          <Form.Item
            name="take_profit_pct"
            label="止盈阈值 (小数)"
            style={{ flex: 1 }}
          >
            <InputNumber
              style={{ width: '100%' }}
              step={0.01}
              min={0}
              max={10}
              placeholder="0.30 = +30%"
            />
          </Form.Item>
          <Form.Item name="take_profit_type" label="止盈类型" style={{ flex: 1 }}>
            <Select
              options={[
                { value: 'pct_from_cost', label: '成本百分比' },
              ]}
            />
          </Form.Item>
        </Space>
        <Form.Item
          name="peak_price"
          label="追踪峰值价 (仅 trailing 类型)"
          tooltip="追踪止损模式中跟踪的最高价；可手动重置"
        >
          <InputNumber style={{ width: '100%' }} step={0.01} min={0} placeholder="留空" />
        </Form.Item>
        <Form.Item name="enabled" label="启用" valuePropName="checked">
          <Switch />
        </Form.Item>
      </Form>
    </Modal>
  );
}

// ── Risk Rules Tab ─────────────────────────────────────────────────────

function RiskRulesTab() {
  const { message } = useAntdStatic();
  const [rules, setRules] = useState<HoldingRiskRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<HoldingRiskRule | null>(null);

  const fetchRules = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listRiskRules();
      setRules(data);
    } catch {
      message.error('获取规则列表失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    fetchRules();
  }, [fetchRules]);

  const handleCreate = () => {
    setEditing(null);
    setModalOpen(true);
  };

  const handleEdit = (r: HoldingRiskRule) => {
    setEditing(r);
    setModalOpen(true);
  };

  const handleSave = async (
    payload: RiskRuleCreate & { peak_price?: number | null },
  ) => {
    try {
      if (editing) {
        await updateRiskRule(editing.id, {
          stop_loss_pct: payload.stop_loss_pct,
          stop_loss_type: payload.stop_loss_type,
          take_profit_pct: payload.take_profit_pct,
          take_profit_type: payload.take_profit_type,
          peak_price: payload.peak_price,
          enabled: payload.enabled,
        });
        message.success('已更新');
      } else {
        await createRiskRule(payload);
        message.success('已新增');
      }
      setModalOpen(false);
      fetchRules();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '保存失败';
      message.error(msg);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteRiskRule(id);
      message.success('已删除');
      fetchRules();
    } catch {
      message.error('删除失败');
    }
  };

  const handleToggle = async (r: HoldingRiskRule, enabled: boolean) => {
    try {
      await updateRiskRule(r.id, { enabled });
      message.success(enabled ? '已启用' : '已停用');
      fetchRules();
    } catch {
      message.error('更新失败');
    }
  };

  const columns: ColumnsType<HoldingRiskRule> = [
    {
      title: '股票代码',
      dataIndex: 'stock_code',
      width: 120,
      render: (v: string) => <code style={{ fontSize: 13 }}>{v}</code>,
    },
    {
      title: '止损',
      width: 180,
      render: (_: unknown, r: HoldingRiskRule) => (
        <span>
          <Tag color={r.stop_loss_pct == null ? 'default' : 'orange'}>
            {formatPct(r.stop_loss_pct)}
          </Tag>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {STOP_LOSS_TYPE_LABELS[r.stop_loss_type] ?? r.stop_loss_type}
          </Text>
        </span>
      ),
    },
    {
      title: '止盈',
      width: 140,
      render: (_: unknown, r: HoldingRiskRule) => (
        <Tag color={r.take_profit_pct == null ? 'default' : 'green'}>
          {formatPct(r.take_profit_pct)}
        </Tag>
      ),
    },
    {
      title: '追踪峰值',
      dataIndex: 'peak_price',
      width: 110,
      render: (v: number | null) => (v == null ? '—' : `¥${v.toFixed(2)}`),
    },
    {
      title: '状态',
      width: 140,
      render: (_: unknown, r: HoldingRiskRule) =>
        r.triggered_at ? (
          <Tooltip title={r.trigger_reason ?? ''}>
            <Tag color="red">已触发</Tag>
          </Tooltip>
        ) : r.enabled ? (
          <Tag color="success">监控中</Tag>
        ) : (
          <Tag>已停用</Tag>
        ),
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      width: 80,
      render: (enabled: boolean, record: HoldingRiskRule) => (
        <Switch
          size="small"
          checked={enabled}
          onChange={(v) => handleToggle(record, v)}
        />
      ),
    },
    {
      title: '操作',
      width: 140,
      render: (_: unknown, record: HoldingRiskRule) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          />
          <Popconfirm
            title={`确认删除 ${record.stock_code} 的规则?`}
            onConfirm={() => handleDelete(record.id)}
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
          marginBottom: 12,
        }}
      >
        <Text type="secondary">
          按持仓股票配置止损/止盈规则。盘中 intraday_price_poll 任务（每 5 分钟）会根据实时价格评估并触发告警。
        </Text>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
          新增规则
        </Button>
      </div>
      <Table<HoldingRiskRule>
        rowKey="id"
        columns={columns}
        dataSource={rules}
        loading={loading}
        pagination={false}
        size="middle"
      />
      <RiskRuleModal
        open={modalOpen}
        initial={editing}
        onCancel={() => setModalOpen(false)}
        onSave={handleSave}
      />
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────

export default function MonitoringPage() {
  return (
    <div>
      <PageHeader
        title="监控配置"
        enLabel="Monitoring"
        icon={<BellOutlined />}
        description="通知通道 + 持仓止损止盈规则"
      />
      <Card variant="borderless" style={{ background: 'transparent' }}>
        <Tabs
          defaultActiveKey="channels"
          items={[
            {
              key: 'channels',
              label: (
                <span>
                  <BellOutlined /> 通知通道
                </span>
              ),
              children: <ChannelsTab />,
            },
            {
              key: 'risk_rules',
              label: (
                <span>
                  <SafetyCertificateOutlined /> 止损止盈规则
                </span>
              ),
              children: <RiskRulesTab />,
            },
          ]}
        />
      </Card>
    </div>
  );
}
