import { useEffect, useState } from 'react';
import {
  Button, Card, Col, Row, Tag, Space, Typography, Popconfirm, Modal, Form, Input, Select, Empty, Spin,
} from 'antd';
import { PlayCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { useAntdStatic } from '../hooks/useAntdStatic';
import PageHeader from '../components/PageHeader';
import { listPlans, createPlan, updatePlan, deletePlan, runPlan, listStrategies } from '../api/client';
import type { PlanResponse, StrategyResponse } from '../api/types';

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  active: { color: 'green', label: '运行中' },
  paused: { color: 'orange', label: '已暂停' },
  archived: { color: 'default', label: '已归档' },
};

const LOGIC_MAP: Record<string, string> = { AND: '全部满足', OR: '任一满足' };

const SCOPE_MAP: Record<string, string> = {
  all_stocks: '全市场',
  industries: '指定行业',
  index: '指数成分',
  watchlist: '自选股',
  custom: '自定义列表',
};

export default function PlansPage() {
  const { message } = useAntdStatic();
  const [plans, setPlans] = useState<PlanResponse[]>([]);
  const [strategies, setStrategies] = useState<StrategyResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const [ps, ss] = await Promise.all([listPlans(), listStrategies()]);
      setPlans(ps);
      setStrategies(ss);
    } catch { message.error('加载失败'); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      const strategyIds = values.strategy_ids?.map((id: string) => Number(id)) || [];
      await createPlan({
        name: values.name,
        slug: values.slug,
        description: values.description || '',
        strategy_composition: { strategy_ids: strategyIds, logic: values.logic || 'AND' },
        scan_scope: { type: values.scope_type || 'all_stocks', values: values.scope_values?.split(',').map((s: string) => s.trim()).filter(Boolean) || [] },
      });
      message.success('预案已创建');
      setCreateOpen(false);
      load();
    } catch { /* validation */ }
  };

  const handleRun = async (id: number) => {
    try {
      const result = await runPlan(id) as Record<string, unknown>;
      message.success(`扫描完成: ${result.passed ?? 0} 只通过, ${result.drafts_emitted ?? 0} 条草稿`);
      load();
    } catch { message.error('运行失败'); }
  };

  const handleToggle = async (p: PlanResponse) => {
    const newStatus = p.status === 'active' ? 'paused' : 'active';
    await updatePlan(p.id, { status: newStatus });
    message.success(`已${newStatus === 'active' ? '启用' : '暂停'}`);
    load();
  };

  const handleDelete = async (id: number) => {
    await deletePlan(id);
    message.success('已删除');
    load();
  };

  const strategyName = (id: number) => strategies.find(s => s.id === id)?.name || `#${id}`;

  return (
    <div>
      <PageHeader
        title="筛选预案"
        enLabel="Plans"
        extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => {
          form.resetFields();
          form.setFieldsValue({ logic: 'AND', scope_type: 'all_stocks' });
          setCreateOpen(true);
        }}>新建预案</Button>}
      />

      <Spin spinning={loading}>
        {plans.length === 0 && !loading ? (
          <Empty description="暂无预案" />
        ) : (
          <Row gutter={[16, 16]}>
            {plans.map(p => (
              <Col key={p.id} xs={24} sm={12} lg={8}>
                <Card
                  title={
                    <Space>
                      <span>{p.name}</span>
                      <Tag color={STATUS_MAP[p.status]?.color}>{STATUS_MAP[p.status]?.label}</Tag>
                      {p.is_builtin && <Tag color="gold">内置</Tag>}
                    </Space>
                  }
                  extra={
                    <Space>
                      <Button size="small" icon={<PlayCircleOutlined />} onClick={() => handleRun(p.id)}>
                        运行
                      </Button>
                      {!p.is_builtin && (
                        <Popconfirm title="确定删除？" onConfirm={() => handleDelete(p.id)}>
                          <Button size="small" danger>删除</Button>
                        </Popconfirm>
                      )}
                    </Space>
                  }
                >
                  <div style={{ marginBottom: 8 }}>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>{p.description}</Typography.Text>
                  </div>
                  <div style={{ marginBottom: 8 }}>
                    <Tag color={p.strategy_composition.logic === 'AND' ? 'blue' : 'orange'}>
                      {LOGIC_MAP[p.strategy_composition.logic] ?? p.strategy_composition.logic}
                    </Tag>
                    {p.strategy_composition.strategy_ids.map(id => (
                      <Tag key={id}>{strategyName(id)}</Tag>
                    ))}
                  </div>
                  <Space size="small" style={{ fontSize: 12 }}>
                    <span>范围: {SCOPE_MAP[p.scan_scope.type] ?? p.scan_scope.type}</span>
                    {p.trading_rules && <Tag color="purple">有交易规则</Tag>}
                    <span>候选: {p.candidate_count}</span>
                  </Space>
                  <div style={{ marginTop: 8 }}>
                    <Button size="small" onClick={() => handleToggle(p)}>
                      {p.status === 'active' ? '暂停' : '启用'}
                    </Button>
                  </div>
                </Card>
              </Col>
            ))}
          </Row>
        )}
      </Spin>

      <Modal title="新建预案" open={createOpen} onOk={handleCreate}
        onCancel={() => setCreateOpen(false)} width={600} destroyOnHidden>
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="name" label="名称" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="slug" label="Slug" rules={[{ required: true, pattern: /^[a-z][a-z0-9_]*$/ }]}>
                <Input placeholder="lowercase_underscore" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="strategy_ids" label="策略" rules={[{ required: true }]}>
            <Select mode="multiple" placeholder="选择策略"
              options={strategies.map(s => ({ value: String(s.id), label: s.name }))} />
          </Form.Item>
          <Form.Item name="logic" label="组合逻辑">
            <Select options={[{ value: 'AND', label: '全部满足 (AND)' }, { value: 'OR', label: '任一满足 (OR)' }]} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="scope_type" label="扫描范围">
                <Select options={[
                  { value: 'all_stocks', label: '全市场' },
                  { value: 'industries', label: '指定行业' },
                  { value: 'watchlist', label: '自选股' },
                  { value: 'custom', label: '自定义列表' },
                ]} />
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
    </div>
  );
}
