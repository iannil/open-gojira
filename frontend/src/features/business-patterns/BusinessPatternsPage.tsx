import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Button,
  Card,
  Col,
  Modal,
  Form,
  Input,
  Select,
  Row,
  Space,
  Tag,
  Typography,
  Tooltip,
  Popconfirm,
  Divider,
} from 'antd';
import {
  LockOutlined,
  PlusOutlined,
  DeleteOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';

import { PageHeader, EmptyState } from '../../components/primitives';
import QueryBoundary from '../../components/QueryBoundary';
import { listThemes } from '../../api/client';
import { useBusinessPatternsQuery } from './useBusinessPatternQueries';
import {
  useCreateBusinessPatternMutation,
  useDeleteBusinessPatternMutation,
  useInferAllBusinessPatternsMutation,
  useUpdateBusinessPatternMutation,
} from './useBusinessPatternMutations';
import type {
  BusinessPattern,
  BusinessPatternCreate,
  BusinessPatternUpdate,
  ThesisVariableTemplate,
} from '../../api/types';

const TIER_LABELS: Record<number, { label: string; color: string }> = {
  0: { label: '0 层选择权(被选择)', color: 'red' },
  1: { label: '1 层选择权(双向)', color: 'default' },
  2: { label: '2 层选择权(稀缺)', color: 'blue' },
  3: { label: '3 层选择权(垄断)', color: 'gold' },
};

const SOURCE_LABELS: Record<string, string> = {
  manual: '手动',
  lixinger: 'Lixinger',
};

interface FormShape {
  name: string;
  theme_id?: number | null;
  description?: string;
  first_principle_variable?: string;
  power_tier_baseline: number;
  thesis_variables: ThesisVariableTemplate[];
  lixinger_industries: string[];
}

function industriesToStr(arr: string[]): string {
  return arr.join(',');
}

function parseIndustriesStr(s: string): string[] {
  return s
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean);
}

export default function BusinessPatternsPage() {
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<BusinessPattern | null>(null);
  const [form] = Form.useForm<FormShape>();

  const patternsQ = useBusinessPatternsQuery();
  // Themes — re-using strategies' query since themes are global
  // (if useThemesQuery doesn't exist, fall back to fetch directly)
  const themesQ = useThemesQuerySafe();
  const createM = useCreateBusinessPatternMutation();
  const updateM = useUpdateBusinessPatternMutation();
  const deleteM = useDeleteBusinessPatternMutation();
  const inferM = useInferAllBusinessPatternsMutation();

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      power_tier_baseline: 0,
      thesis_variables: [],
      lixinger_industries: [],
    });
    setModalOpen(true);
  };

  const openEdit = (p: BusinessPattern) => {
    setEditing(p);
    form.setFieldsValue({
      name: p.name,
      theme_id: p.theme_id ?? undefined,
      description: p.description ?? '',
      first_principle_variable: p.first_principle_variable ?? '',
      power_tier_baseline: p.power_tier_baseline,
      thesis_variables: p.thesis_variables,
      lixinger_industries: p.lixinger_industries,
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    let values: FormShape;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    if (editing) {
      // Builtin: only description editable; backend will reject other field changes.
      // User-created: all fields editable.
      const payload: BusinessPatternUpdate = editing.is_builtin
        ? { description: values.description ?? '' }
        : {
            name: values.name,
            theme_id: values.theme_id ?? null,
            description: values.description,
            first_principle_variable: values.first_principle_variable,
            power_tier_baseline: values.power_tier_baseline,
            thesis_variables: values.thesis_variables,
            lixinger_industries: values.lixinger_industries,
          };
      await updateM.mutateAsync({ id: editing.id, payload });
    } else {
      const payload: BusinessPatternCreate = {
        name: values.name,
        theme_id: values.theme_id ?? null,
        description: values.description,
        first_principle_variable: values.first_principle_variable,
        power_tier_baseline: values.power_tier_baseline,
        thesis_variables: values.thesis_variables,
        lixinger_industries: values.lixinger_industries,
      };
      await createM.mutateAsync(payload);
    }
    setModalOpen(false);
  };

  return (
    <div>
      <PageHeader
        title="商业模式"
        enLabel="Business Patterns"
        purpose="商业模式 = 一类生意的「核心变量 + 选择权位阶 + 论点变量」模板(煤化工/电解铝/药店零售/银行...)。基于 invest1/2/3 文档方法论。"
        flow={[
          { label: '商业模式' },
          { to: '/review', label: '审计' },
        ]}
        actions={
          <Space>
            <Tooltip title="批量重新推断所有股票的商业模式关联(跳过用户已手动覆盖的)">
              <Button
                icon={<ThunderboltOutlined />}
                onClick={() => inferM.mutate(false)}
                loading={inferM.isPending}
              >
                重新推断
              </Button>
            </Tooltip>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建模式
            </Button>
          </Space>
        }
      />

      <QueryBoundary
        query={patternsQ}
        isEmpty={(data) => data.length === 0}
        emptyRender={
          <EmptyState
            variant="cold"
            title="还没有商业模式"
            description="商业模式是「产业研究」的第一公民,承载 invest1/2/3 文档里的第一性原理核心变量、'求'字理论位阶、论点变量模板。重启后端会自动 seed ~17 个内置模式。"
            cta={{ label: '创建第一个模式', onClick: openCreate }}
          />
        }
      >
        {(patterns) => (
          <Row gutter={[16, 16]}>
            {patterns.map((p) => {
              const tier = TIER_LABELS[p.power_tier_baseline] ?? {
                label: `${p.power_tier_baseline}`,
                color: 'default',
              };
              const themeName =
                themesQ.data?.find((t) => t.id === p.theme_id)?.name ?? null;
              return (
                <Col key={p.id} xs={24} sm={12} lg={8} xl={6}>
                  <Card
                    className="gojira-card"
                    bordered={false}
                    title={
                      <Space>
                        {p.is_builtin && <LockOutlined />}
                        {p.name}
                      </Space>
                    }
                    extra={
                      <Space>
                        <Button size="small" onClick={() => openEdit(p)}>
                          {p.is_builtin ? '查看' : '编辑'}
                        </Button>
                        {!p.is_builtin && (
                          <Popconfirm
                            title="确定删除？引用此模式的股票会被清空关联。"
                            onConfirm={() => deleteM.mutate(p.id)}
                          >
                            <Button size="small" danger loading={deleteM.isPending}>
                              删除
                            </Button>
                          </Popconfirm>
                        )}
                      </Space>
                    }
                    style={{ height: '100%' }}
                  >
                    {p.first_principle_variable && (
                      <div style={{ marginBottom: 'var(--sp-2)' }}>
                        <Typography.Text type="secondary" style={{ fontSize: 'var(--fs-xs)' }}>
                          核心变量
                        </Typography.Text>
                        <div
                          style={{
                            fontWeight: 500,
                            color: 'var(--gojira-primary, #4F6D93)',
                          }}
                        >
                          {p.first_principle_variable}
                        </div>
                      </div>
                    )}

                    {p.description && (
                      <Typography.Paragraph
                        type="secondary"
                        style={{ fontSize: 'var(--fs-sm)', marginBottom: 'var(--sp-2)' }}
                        ellipsis={{ rows: 3 }}
                      >
                        {p.description}
                      </Typography.Paragraph>
                    )}

                    <Space size={4} wrap style={{ marginBottom: 'var(--sp-2)' }}>
                      <Tag color={tier.color}>{tier.label}</Tag>
                      {themeName && <Tag color="purple">{themeName}</Tag>}
                      {p.is_builtin ? (
                        <Tag color="gold">内置</Tag>
                      ) : (
                        <Tag>自定义</Tag>
                      )}
                    </Space>

                    {p.thesis_variables.length > 0 && (
                      <>
                        <Divider style={{ margin: '8px 0' }} />
                        <Typography.Text
                          type="secondary"
                          style={{ fontSize: 'var(--fs-xs)' }}
                        >
                          论点变量 ({p.thesis_variables.length})
                        </Typography.Text>
                        <div style={{ marginTop: 4 }}>
                          <Space size={4} wrap>
                            {p.thesis_variables.slice(0, 6).map((v, i) => (
                              <Tag key={i} style={{ fontSize: 'var(--fs-xs)' }}>
                                {v.name}
                                <span style={{ opacity: 0.5, marginLeft: 4 }}>
                                  {SOURCE_LABELS[v.source] ?? v.source}
                                </span>
                              </Tag>
                            ))}
                            {p.thesis_variables.length > 6 && (
                              <Tag>+{p.thesis_variables.length - 6}</Tag>
                            )}
                          </Space>
                        </div>
                      </>
                    )}

                    {p.lixinger_industries.length > 0 && (
                      <div style={{ marginTop: 'var(--sp-2)' }}>
                        <Typography.Text
                          type="secondary"
                          style={{ fontSize: 'var(--fs-xs)' }}
                        >
                          自动关联:Lixinger 行业
                        </Typography.Text>
                        <div style={{ marginTop: 4 }}>
                          <Space size={4} wrap>
                            {p.lixinger_industries.map((ind) => (
                              <Tag
                                key={ind}
                                style={{ fontSize: 'var(--fs-xs)' }}
                                color="default"
                              >
                                {ind}
                              </Tag>
                            ))}
                          </Space>
                        </div>
                      </div>
                    )}

                    {p.source_ref && (
                      <div style={{ marginTop: 'var(--sp-2)' }}>
                        <Typography.Text
                          type="secondary"
                          style={{ fontSize: 'var(--fs-xs)' }}
                        >
                          📖 {p.source_ref}
                        </Typography.Text>
                      </div>
                    )}
                  </Card>
                </Col>
              );
            })}
          </Row>
        )}
      </QueryBoundary>

      <Modal
        title={editing ? (editing.is_builtin ? '查看内置模式' : '编辑模式') : '新建商业模式'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={createM.isPending || updateM.isPending}
        width={720}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="name"
                label="模式名"
                rules={[{ required: true, min: 1, max: 80 }]}
              >
                <Input
                  placeholder="如:煤化工 / 药店零售 / 银行"
                  disabled={!!editing?.is_builtin}
                />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="theme_id" label="安全主线">
                <Select
                  allowClear
                  placeholder="归类"
                  disabled={!!editing?.is_builtin}
                  options={(themesQ.data ?? []).map((t) => ({
                    value: t.id,
                    label: t.name,
                  }))}
                />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item
                name="power_tier_baseline"
                label="'求'字位阶"
                rules={[{ required: true }]}
              >
                <Select
                  disabled={!!editing?.is_builtin}
                  options={Object.entries(TIER_LABELS).map(([k, v]) => ({
                    value: Number(k),
                    label: v.label,
                  }))}
                />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="first_principle_variable" label="第一性原理核心变量">
            <Input
              placeholder="如:煤油价差套利 / 数店面 / 电力成本"
              disabled={!!editing?.is_builtin}
            />
          </Form.Item>

          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="补充核心变量没说清的细节" />
          </Form.Item>

          <Form.Item
            name="lixinger_industries"
            label="自动关联:Lixinger 行业"
            tooltip="声明该模式覆盖哪些 Lixinger industry 字符串。1:1 → 自动 set;1:0 或 1:多 → 留 null 强制手标。用逗号分隔。"
            getValueFromEvent={(e) => parseIndustriesStr(e.target.value)}
            getValueProps={(v) => ({ value: industriesToStr(v ?? []) })}
          >
            <Input
              placeholder="如:煤炭开采,化学原料"
              disabled={!!editing?.is_builtin}
            />
          </Form.Item>

          <Divider>论点变量</Divider>
          <Form.List name="thesis_variables">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...rest }) => (
                  <Row key={key} gutter={8} style={{ marginBottom: 8 }}>
                    <Col span={8}>
                      <Form.Item
                        {...rest}
                        name={[name, 'name']}
                        rules={[{ required: true, message: '必填' }]}
                      >
                        <Input
                          placeholder="变量名"
                          disabled={!!editing?.is_builtin}
                        />
                      </Form.Item>
                    </Col>
                    <Col span={5}>
                      <Form.Item {...rest} name={[name, 'unit']}>
                        <Input placeholder="单位" disabled={!!editing?.is_builtin} />
                      </Form.Item>
                    </Col>
                    <Col span={7}>
                      <Form.Item
                        {...rest}
                        name={[name, 'source']}
                        rules={[{ required: true }]}
                      >
                        <Select
                          disabled={!!editing?.is_builtin}
                          options={[
                            { value: 'manual', label: '手动' },
                            { value: 'lixinger', label: 'Lixinger 自动 sync' },
                          ]}
                        />
                      </Form.Item>
                    </Col>
                    <Col span={4}>
                      {!editing?.is_builtin && (
                        <Button
                          type="text"
                          danger
                          icon={<DeleteOutlined />}
                          onClick={() => remove(name)}
                        />
                      )}
                    </Col>
                  </Row>
                ))}
                {!editing?.is_builtin && (
                  <Button
                    type="dashed"
                    block
                    onClick={() =>
                      add({ name: '', unit: '', source: 'manual' })
                    }
                  >
                    + 添加变量
                  </Button>
                )}
              </>
            )}
          </Form.List>
        </Form>
      </Modal>
    </div>
  );
}

/** Themes list (used for the theme_id select dropdown). */
function useThemesQuerySafe() {
  return useQuery({
    queryKey: ['themes'],
    queryFn: () => listThemes(),
    staleTime: 5 * 60_000,
  });
}
