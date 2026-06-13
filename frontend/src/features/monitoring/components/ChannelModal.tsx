import { useEffect, useState } from 'react';
import { Form, Input, Modal, Select, Switch } from 'antd';
import type {
  NotificationChannel,
  NotificationChannelCreate,
  NotificationChannelType,
  NotificationSeverityFilter,
} from '../../../api/types';
import { useAntdStatic } from '../../../hooks/useAntdStatic';

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

interface ChannelFormValues {
  name: string;
  type: NotificationChannelType;
  config_text: string;
  enabled: boolean;
  severity_filter: NotificationSeverityFilter;
}

export interface ChannelModalProps {
  open: boolean;
  initial: NotificationChannel | null;
  onCancel: () => void;
  onSave: (payload: NotificationChannelCreate) => Promise<void>;
}

export default function ChannelModal({
  open,
  initial,
  onCancel,
  onSave,
}: ChannelModalProps) {
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
        <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入通道名称' }]}>
          <Input placeholder="如 wechat_main" disabled={!!initial} />
        </Form.Item>
        <Form.Item name="type" label="类型" rules={[{ required: true }]}>
          <Select
            options={Object.entries(CHANNEL_TYPE_LABELS).map(([v, label]) => ({ value: v, label }))}
            disabled={!!initial}
          />
        </Form.Item>
        <Form.Item
          name="config_text"
          label="配置 (JSON)"
          tooltip="server_chan: {sendkey}; email: {to, smtp_host, smtp_user, smtp_pass}; dingtalk_webhook: {webhook_url}; telegram_bot: {bot_token, chat_id}"
          rules={[{ required: true }]}
        >
          <Input.TextArea
            rows={4}
            style={{ fontFamily: 'var(--font-numeric)', fontSize: 'var(--fs-xs)' }}
          />
        </Form.Item>
        <Form.Item name="severity_filter" label="告警级别过滤">
          <Select
            options={Object.entries(SEVERITY_LABELS).map(([v, label]) => ({ value: v, label }))}
          />
        </Form.Item>
        <Form.Item name="enabled" label="启用" valuePropName="checked">
          <Switch />
        </Form.Item>
      </Form>
    </Modal>
  );
}
