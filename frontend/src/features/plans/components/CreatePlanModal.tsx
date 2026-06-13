import { Form, Input, Modal, Row, Col, Select } from 'antd';
import type { PlanCreate, StrategyResponse } from '../../../api/types';

interface FormValues {
  name: string;
  slug: string;
  description?: string;
  strategy_ids?: string[];
  logic?: 'AND' | 'OR';
  scope_type?: string;
  scope_values?: string;
}

export interface CreatePlanModalProps {
  open: boolean;
  strategies: StrategyResponse[] | undefined;
  submitting: boolean;
  onCancel: () => void;
  onSubmit: (payload: PlanCreate) => Promise<void>;
}

function buildPayload(v: FormValues): PlanCreate {
  const strategyIds = v.strategy_ids?.map((id) => Number(id)) ?? [];
  return {
    name: v.name,
    slug: v.slug,
    description: v.description ?? '',
    strategy_composition: {
      strategy_ids: strategyIds,
      logic: v.logic ?? 'AND',
    },
    scan_scope: {
      type: (v.scope_type ?? 'all_stocks') as PlanCreate['scan_scope']['type'],
      values:
        v.scope_values?.split(',').map((s) => s.trim()).filter(Boolean) ?? [],
    },
  };
}

export default function CreatePlanModal({
  open,
  strategies,
  submitting,
  onCancel,
  onSubmit,
}: CreatePlanModalProps) {
  const [form] = Form.useForm<FormValues>();

  const handleOk = async () => {
    let values: FormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    try {
      await onSubmit(buildPayload(values));
    } catch {
      // toast + invalidate handled by useToastMutation
    }
  };

  return (
    <Modal
      title="新建预案"
      open={open}
      onOk={handleOk}
      onCancel={onCancel}
      confirmLoading={submitting}
      width={600}
      destroyOnHidden
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{ logic: 'AND', scope_type: 'all_stocks' }}
      >
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="name" label="名称" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="slug"
              label="Slug"
              rules={[{ required: true, pattern: /^[a-z][a-z0-9_]*$/ }]}
            >
              <Input placeholder="lowercase_underscore" />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item name="description" label="描述">
          <Input.TextArea rows={2} />
        </Form.Item>
        <Form.Item name="strategy_ids" label="策略" rules={[{ required: true }]}>
          <Select
            mode="multiple"
            placeholder="选择策略"
            options={(strategies ?? []).map((s) => ({
              value: String(s.id),
              label: s.name,
            }))}
          />
        </Form.Item>
        <Form.Item name="logic" label="组合逻辑">
          <Select
            options={[
              { value: 'AND', label: '全部满足 (AND)' },
              { value: 'OR', label: '任一满足 (OR)' },
            ]}
          />
        </Form.Item>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="scope_type" label="扫描范围">
              <Select
                options={[
                  { value: 'all_stocks', label: '全市场' },
                  { value: 'industries', label: '指定行业' },
                  { value: 'watchlist', label: '自选股' },
                  { value: 'custom', label: '自定义列表' },
                ]}
              />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="scope_values" label="范围值 (逗号分隔)">
              <Input placeholder="行业/代码列表, 逗号分隔" />
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </Modal>
  );
}
