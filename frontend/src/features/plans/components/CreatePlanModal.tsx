import { Form, Input, Modal, Row, Col, Select, Switch } from 'antd';
import {
  CYCLE_BUY_MAX_OPTIONS,
  type CycleBuyMax,
  type PlanCreate,
  type StrategyResponse,
} from '../../../api/types';

interface FormValues {
  name: string;
  slug: string;
  description?: string;
  strategy_ids?: string[];
  logic?: 'AND' | 'OR';
  scope_type?: string;
  scope_values?: string;
  cycle_buy_max?: CycleBuyMax;
  disable_midstream_filter?: boolean;
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
    cycle_buy_max: v.cycle_buy_max ?? 'mid',
    disable_midstream_filter: v.disable_midstream_filter ?? false,
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
        initialValues={{
          logic: 'AND',
          scope_type: 'all_stocks',
          cycle_buy_max: 'mid',
          disable_midstream_filter: false,
        }}
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
        <Row gutter={16}>
          <Col span={14}>
            <Form.Item
              name="cycle_buy_max"
              label="周期买入上限 (G1)"
              tooltip="invest3 §5: 大盘整体高位时不要融资加杠杆。当前 cycle 高于此阈值时 plan_runner 抑制 BUY drafts。"
            >
              <Select options={CYCLE_BUY_MAX_OPTIONS} />
            </Form.Item>
          </Col>
          <Col span={10}>
            <Form.Item
              name="disable_midstream_filter"
              label="关闭中游过滤 (G2)"
              valuePropName="checked"
              tooltip="invest3 §13: 中游企业除非成本最低,否则剔除。开关 = 跳过此过滤(用于逆向等特殊场景)。"
            >
              <Switch />
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </Modal>
  );
}
