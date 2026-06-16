import { useEffect, useState } from 'react';
import { Form, Input, InputNumber, Modal, Radio, message } from 'antd';

import {
  approveClaimVariable,
  patchClaimVariable,
} from '../../../api/client';
import type { BreachWhen, ResearchClaimVariable } from '../../../api/types';

interface Props {
  open: boolean;
  variable: ResearchClaimVariable | null;
  onClose: () => void;
  onSaved: () => void;
}

interface FormShape {
  threshold_critical: number;
  breach_when: BreachWhen;
  unit?: string;
  window_periods?: number;
  note?: string;
}

export default function EditClaimVariableModal({ open, variable, onClose, onSaved }: Props) {
  const [form] = Form.useForm<FormShape>();
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open && variable) {
      form.setFieldsValue({
        threshold_critical: variable.threshold_critical,
        breach_when: variable.breach_when,
        unit: variable.unit || '',
        window_periods: variable.window_periods ?? undefined,
        note: '',
      });
    }
  }, [open, variable, form]);

  if (!variable) return null;

  const isProposed = variable.status === 'proposed';

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      if (isProposed) {
        await approveClaimVariable(variable.id, {
          threshold_critical: values.threshold_critical,
          breach_when: values.breach_when,
          unit: values.unit || undefined,
          window_periods: values.window_periods,
          note: values.note || undefined,
        });
        message.success('已激活');
      } else {
        await patchClaimVariable(variable.id, {
          threshold_critical: values.threshold_critical,
          breach_when: values.breach_when,
          unit: values.unit || undefined,
          window_periods: values.window_periods,
          note: values.note || undefined,
        });
        message.success('已保存');
      }
      onSaved();
    } catch (e) {
      if (e && typeof e === 'object' && 'errorFields' in e) return;  // form validation
      message.error('保存失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      title={isProposed ? '编辑提议后激活' : '编辑 active var'}
      onCancel={onClose}
      onOk={handleSubmit}
      okText={isProposed ? 'Approve with edits' : 'Save changes'}
      confirmLoading={submitting}
      destroyOnClose
    >
      <Form form={form} layout="vertical">
        <Form.Item label="变量名">
          <span>{variable.variable_name}</span>
        </Form.Item>
        <Form.Item label="数据源">
          <span style={{ fontFamily: 'monospace' }}>{variable.source}</span>
        </Form.Item>
        <Form.Item
          name="threshold_critical"
          label="阈值"
          rules={[{ required: true, message: '必填' }]}
        >
          <InputNumber style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item
          name="breach_when"
          label="告警方向 (字面对齐 signal 文本比较符)"
          rules={[{ required: true }]}
        >
          <Radio.Group>
            <Radio value="lt">{'<'} 阈值 (低于阈值时告警)</Radio>
            <Radio value="gt">{'>'} 阈值 (高于阈值时告警)</Radio>
          </Radio.Group>
        </Form.Item>
        <Form.Item name="window_periods" label="连续 N 期 breach 才告警 (留空=单点)">
          <InputNumber min={1} max={12} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="unit" label="单位 (% / 倍 / 空)">
          <Input />
        </Form.Item>
        <Form.Item name="note" label="备注 (可选)">
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
