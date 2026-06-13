import { useEffect, useState } from 'react';
import { Form, Input, InputNumber, Modal, Select, Space, Switch } from 'antd';
import type {
  HoldingRiskRule,
  RiskRuleCreate,
  StopLossType,
  TakeProfitType,
} from '../../../api/types';

const STOP_LOSS_TYPE_LABELS: Record<StopLossType, string> = {
  pct_from_cost: '成本百分比',
  trailing: '追踪止损',
  fixed_price: '固定价格',
};

interface RiskRuleFormValues {
  stock_code: string;
  stop_loss_pct: number | null;
  stop_loss_type: StopLossType;
  take_profit_pct: number | null;
  take_profit_type: TakeProfitType;
  peak_price: number | null;
  enabled: boolean;
}

export interface RiskRuleModalProps {
  open: boolean;
  initial: HoldingRiskRule | null;
  onCancel: () => void;
  onSave: (payload: RiskRuleCreate & { peak_price?: number | null }) => Promise<void>;
}

export default function RiskRuleModal({
  open,
  initial,
  onCancel,
  onSave,
}: RiskRuleModalProps) {
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
          <Form.Item name="take_profit_pct" label="止盈阈值 (小数)" style={{ flex: 1 }}>
            <InputNumber
              style={{ width: '100%' }}
              step={0.01}
              min={0}
              max={10}
              placeholder="0.30 = +30%"
            />
          </Form.Item>
          <Form.Item name="take_profit_type" label="止盈类型" style={{ flex: 1 }}>
            <Select options={[{ value: 'pct_from_cost', label: '成本百分比' }]} />
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
