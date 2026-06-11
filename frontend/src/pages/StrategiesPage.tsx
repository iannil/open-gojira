import { useEffect, useState } from 'react';
import {
  Button, Card, Col, Modal, Form, Input, Select, Row, Space, Tag, Typography, Empty, Tooltip, Popconfirm,
} from 'antd';
import { LockOutlined, ThunderboltOutlined, PlusOutlined } from '@ant-design/icons';
import { useAntdStatic } from '../hooks/useAntdStatic';
import PageHeader from '../components/PageHeader';
import {
  listStrategies, createStrategy, updateStrategy, deleteStrategy, testStrategy,
} from '../api/client';
import type { StrategyResponse, StrategyCondition } from '../api/types';

const FIELD_LABELS: Record<string, string> = {
  dyr: '股息率', pe_pct_10y: 'PE分位', pb_pct_10y: 'PB分位',
  dividend_sustainability: '分红可持续', ocf_to_ni: 'OCF/NI',
  qiu_score: '议价能力', industry_in: '行业', security_theme_in: '安全主线',
  bank_blind_box: '银行资产质量', price_drop_pct: '跌幅',
  hq_region_tier: '区域', market_temperature: '市场温度',
};

const OP_LABELS: Record<string, string> = { '>=': '≥', '<=': '≤', '==': '=', 'in': '∈' };

const LOGIC_LABELS: Record<string, string> = { AND: '全部满足', OR: '任一满足' };

function conditionTag(c: StrategyCondition): string {
  const label = FIELD_LABELS[c.field] || c.field;
  const op = OP_LABELS[c.op] || c.op;
  const val = Array.isArray(c.value) ? c.value.join('/') : c.value;
  return `${label} ${op} ${val}`;
}

export default function StrategiesPage() {
  const { message } = useAntdStatic();
  const [strategies, setStrategies] = useState<StrategyResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<StrategyResponse | null>(null);
  const [testModal, setTestModal] = useState<{ id: number; code: string; result?: unknown } | null>(null);
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try { setStrategies(await listStrategies()); } catch { message.error('加载失败'); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ logic: 'AND', conditions: [{ field: 'dyr', op: '>=', value: 0.04 }] });
    setModalOpen(true);
  };

  const openEdit = (s: StrategyResponse) => {
    setEditing(s);
    form.setFieldsValue({
      name: s.name, slug: s.slug, description: s.description,
      logic: s.rule.logic,
      conditions: s.rule.conditions.map(c => ({
        ...c, value: Array.isArray(c.value) ? c.value.join(',') : c.value,
      })),
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const conditions = (values.conditions || []).map((c: StrategyCondition & { value: string }) => ({
        field: c.field, op: c.op,
        value: c.op === 'in' ? c.value.split(',').map((v: string) => v.trim()) : Number(c.value),
      }));
      const payload = {
        name: values.name, slug: values.slug, description: values.description || '',
        rule: { logic: values.logic, conditions },
      };
      if (editing) {
        await updateStrategy(editing.id, { name: payload.name, description: payload.description, rule: payload.rule });
        message.success('策略已更新');
      } else {
        await createStrategy(payload);
        message.success('策略已创建');
      }
      setModalOpen(false);
      load();
    } catch { /* validation */ }
  };

  const handleDelete = async (id: number) => {
    await deleteStrategy(id);
    message.success('已删除');
    load();
  };

  const handleTest = async () => {
    if (!testModal?.code) return;
    try {
      const result = await testStrategy(testModal.id, testModal.code);
      setTestModal({ ...testModal, result });
    } catch { message.error('测试失败'); }
  };

  return (
    <div>
      <PageHeader title="策略库" enLabel="Strategies" extra={<Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建策略</Button>} />

      {strategies.length === 0 && !loading ? (
        <Empty description="暂无策略" />
      ) : (
        <Row gutter={[16, 16]}>
          {strategies.map(s => (
            <Col key={s.id} xs={24} sm={12} lg={8}>
              <Card
                title={<Space>{s.is_builtin && <LockOutlined />}{s.name}</Space>}
                extra={
                  <Space>
                    {!s.is_builtin && (
                      <>
                        <Button size="small" onClick={() => openEdit(s)}>编辑</Button>
                        <Popconfirm title="确定删除？" onConfirm={() => handleDelete(s.id)}>
                          <Button size="small" danger>删除</Button>
                        </Popconfirm>
                      </>
                    )}
                    <Tooltip title="测试策略">
                      <Button size="small" icon={<ThunderboltOutlined />}
                        onClick={() => setTestModal({ id: s.id, code: '' })} />
                    </Tooltip>
                  </Space>
                }
                style={{ height: '100%' }}
              >
                <Typography.Text type="secondary" code style={{ fontSize: 12 }}>{s.slug}</Typography.Text>
                <div style={{ margin: '8px 0' }}>{s.description}</div>
                <div style={{ marginBottom: 8 }}>
                  <Tag color={s.rule.logic === 'AND' ? 'blue' : 'orange'}>{LOGIC_LABELS[s.rule.logic] ?? s.rule.logic}</Tag>
                  {s.rule.conditions.map((c, i) => (
                    <Tag key={i} style={{ margin: 2 }}>{conditionTag(c)}</Tag>
                  ))}
                </div>
                <Tag color={s.kind === 'builtin' ? 'gold' : 'default'}>
                  {s.kind === 'builtin' ? '内置' : '自定义'}
                </Tag>
              </Card>
            </Col>
          ))}
        </Row>
      )}

      <Modal title={editing ? '编辑策略' : '新建策略'} open={modalOpen}
        onOk={handleSubmit} onCancel={() => setModalOpen(false)} width={640} destroyOnHidden>
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="name" label="名称" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="slug" label="Slug" rules={[{ required: true, pattern: /^[a-z][a-z0-9_]*$/ }]}>
                <Input disabled={!!editing} placeholder="lowercase_underscore" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="logic" label="组合逻辑" rules={[{ required: true }]}>
            <Select options={[{ value: 'AND', label: 'AND (全部满足)' }, { value: 'OR', label: 'OR (任一满足)' }]} />
          </Form.Item>
          <Form.List name="conditions">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...rest }) => (
                  <Space key={key} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
                    <Form.Item {...rest} name={[name, 'field']} rules={[{ required: true }]}>
                      <Select style={{ width: 140 }} options={Object.keys(FIELD_LABELS).map(k => ({ value: k, label: FIELD_LABELS[k] }))} />
                    </Form.Item>
                    <Form.Item {...rest} name={[name, 'op']} rules={[{ required: true }]}>
                      <Select style={{ width: 80 }} options={['>=', '<=', '==', 'in'].map(o => ({ value: o, label: OP_LABELS[o] }))} />
                    </Form.Item>
                    <Form.Item {...rest} name={[name, 'value']} rules={[{ required: true }]}>
                      <Input placeholder="值 (in用逗号分隔)" />
                    </Form.Item>
                    <Button type="text" danger onClick={() => remove(name)}>×</Button>
                  </Space>
                ))}
                <Button type="dashed" onClick={() => add({ field: 'dyr', op: '>=', value: '' })} block>
                  + 添加条件
                </Button>
              </>
            )}
          </Form.List>
        </Form>
      </Modal>

      <Modal title="测试策略" open={!!testModal} onOk={handleTest}
        onCancel={() => setTestModal(null)} destroyOnHidden>
        <Input placeholder="输入股票代码" value={testModal?.code || ''}
          onChange={e => testModal && setTestModal({ ...testModal, code: e.target.value })} />
        {testModal?.result != null && (() => {
          const r = testModal.result as Record<string, unknown>;
          return (
            <div style={{ marginTop: 16 }}>
              <Tag color={r?.passed ? 'green' : 'red'}>
                {r?.passed ? '通过' : '未通过'}
              </Tag>
              <pre style={{ fontSize: 12, marginTop: 8, maxHeight: 200, overflow: 'auto' }}>
                {JSON.stringify(r, null, 2)}
              </pre>
            </div>
          );
        })()}
      </Modal>
    </div>
  );
}
