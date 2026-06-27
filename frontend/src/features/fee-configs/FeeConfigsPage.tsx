import { useState } from 'react';
import dayjs from 'dayjs';
import {
  Button,
  DatePicker,
  Form,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import {
  listFeeConfigs,
  createFeeConfig,
  updateFeeConfig,
  deleteFeeConfig,
} from '../../api/client';
import type { BrokerFeeConfig, BrokerFeeConfigCreate } from '../../api/types';
import { PageHeader } from '../../components/primitives';
import PageSection from '../../components/primitives/PageSection';
import QueryBoundary from '../../components/QueryBoundary';

const { Text } = Typography;

function fmtRate(v: number): string {
  return `${(v * 100).toFixed(4)}%`;
}

function fmtDate(v: string): string {
  return v.slice(0, 10);
}

const COLUMNS: ColumnsType<BrokerFeeConfig> = [
  { title: '券商', dataIndex: 'broker_name', width: 100 },
  {
    title: '佣金率',
    dataIndex: 'commission_rate',
    width: 100,
    align: 'right',
    render: (v: number) => fmtRate(v),
  },
  {
    title: '最低佣金',
    dataIndex: 'commission_min',
    width: 100,
    align: 'right',
    render: (v: number) => `¥${v.toFixed(2)}`,
  },
  {
    title: '印花税率',
    dataIndex: 'stamp_duty_rate',
    width: 100,
    align: 'right',
    render: (v: number) => fmtRate(v),
  },
  {
    title: '过户费率',
    dataIndex: 'transfer_fee_rate',
    width: 100,
    align: 'right',
    render: (v: number) => fmtRate(v),
  },
  { title: '生效日', dataIndex: 'effective_from', width: 100, render: (v: string) => fmtDate(v) },
  {
    title: '启用',
    dataIndex: 'is_active',
    width: 60,
    render: (v: boolean) => <Tag color={v ? 'success' : 'default'}>{v ? '是' : '否'}</Tag>,
  },
];

interface FeeConfigForm {
  broker_name: string;
  commission_rate: number;
  commission_min: number;
  stamp_duty_rate: number;
  transfer_fee_rate: number;
  effective_from: any;
  is_active: boolean;
}

const DEFAULT_FORM: FeeConfigForm = {
  broker_name: '',
  commission_rate: 0.00025,
  commission_min: 5,
  stamp_duty_rate: 0.001,
  transfer_fee_rate: 0.00002,
  effective_from: '',
  is_active: true,
};

export default function FeeConfigsPage() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingConfig, setEditingConfig] = useState<BrokerFeeConfig | null>(null);
  const [form] = Form.useForm<FeeConfigForm>();

  const listQ = useQuery({
    queryKey: ['fee-configs'],
    queryFn: () => listFeeConfigs(),
  });

  const createM = useMutation({
    mutationFn: createFeeConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fee-configs'] });
      setModalOpen(false);
      form.resetFields();
    },
  });

  const updateM = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<BrokerFeeConfigCreate> }) =>
      updateFeeConfig(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fee-configs'] });
      setModalOpen(false);
      setEditingConfig(null);
      form.resetFields();
    },
  });

  const deleteM = useMutation({
    mutationFn: deleteFeeConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fee-configs'] });
    },
  });

  const handleOpenCreate = () => {
    setEditingConfig(null);
    form.setFieldsValue(DEFAULT_FORM);
    setModalOpen(true);
  };

  const handleOpenEdit = (cfg: BrokerFeeConfig) => {
    setEditingConfig(cfg);
    form.setFieldsValue({
      broker_name: cfg.broker_name,
      commission_rate: cfg.commission_rate,
      commission_min: cfg.commission_min,
      stamp_duty_rate: cfg.stamp_duty_rate,
      transfer_fee_rate: cfg.transfer_fee_rate,
      effective_from: cfg.effective_from ? dayjs(cfg.effective_from) : undefined,
      is_active: cfg.is_active,
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    const rawDate = values.effective_from;
    let effectiveFrom: string;
    if (!rawDate) {
      effectiveFrom = new Date().toISOString().slice(0, 10);
    } else if (dayjs.isDayjs(rawDate)) {
      effectiveFrom = rawDate.format('YYYY-MM-DD');
    } else if (typeof rawDate === 'string') {
      effectiveFrom = rawDate.slice(0, 10);
    } else {
      effectiveFrom = String(rawDate).slice(0, 10);
    }
    const payload: BrokerFeeConfigCreate = {
      ...values,
      effective_from: effectiveFrom,
    };

    if (editingConfig) {
      updateM.mutate({ id: editingConfig.id, data: payload });
    } else {
      createM.mutate(payload);
    }
  };

  const actionColumns: ColumnsType<BrokerFeeConfig> = [
    ...COLUMNS,
    {
      title: '操作',
      width: 120,
      render: (_, record) => (
        <>
          <Button size="small" type="link" onClick={() => handleOpenEdit(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除此费率配置？"
            onConfirm={() => deleteM.mutate(record.id)}
            okText="确认"
            cancelText="取消"
          >
            <Button size="small" type="link" danger>
              删除
            </Button>
          </Popconfirm>
        </>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="券商费率"
        enLabel="Fee Configs"
        purpose="管理各券商的历史佣金、印花税、过户费配置，用于交易成本计算。"
        actions={
          <Button type="primary" icon={<PlusOutlined />} onClick={handleOpenCreate}>
            新增费率
          </Button>
        }
      />

      <PageSection title="费率列表">
        <QueryBoundary
          query={listQ}
          isEmpty={(data) => data.length === 0}
          emptyRender={<Text type="secondary">暂无费率配置 — 点击「新增费率」创建。</Text>}
        >
          {() => (
            <Table<BrokerFeeConfig>
              columns={actionColumns}
              dataSource={listQ.data!}
              rowKey="id"
              size="small"
              pagination={false}
              scroll={{ x: 900 }}
            />
          )}
        </QueryBoundary>
      </PageSection>

      <Modal
        title={editingConfig ? '编辑费率' : '新增费率'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => {
          setModalOpen(false);
          setEditingConfig(null);
          form.resetFields();
        }}
        confirmLoading={createM.isPending || updateM.isPending}
        okText={editingConfig ? '保存' : '创建'}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="broker_name" label="券商名称" rules={[{ required: true, message: '请输入券商名称' }]}>
            <Select
              placeholder="选择或输入券商"
              options={[
                { value: '华泰证券', label: '华泰证券' },
                { value: '中信证券', label: '中信证券' },
                { value: '招商证券', label: '招商证券' },
                { value: '国泰君安', label: '国泰君安' },
                { value: '广发证券', label: '广发证券' },
              ]}
            />
          </Form.Item>
          <Form.Item name="commission_rate" label="佣金率" rules={[{ required: true, message: '请输入佣金率' }]}>
            <InputNumber
              style={{ width: '100%' }}
              min={0.00001}
              max={0.01}
              step={0.00005}
            />
          </Form.Item>
          <Form.Item name="commission_min" label="最低佣金(元)">
            <InputNumber style={{ width: '100%' }} min={0} step={0.5} />
          </Form.Item>
          <Form.Item name="stamp_duty_rate" label="印花税率">
            <InputNumber
              style={{ width: '100%' }}
              min={0}
              max={0.01}
              step={0.0005}
            />
          </Form.Item>
          <Form.Item name="transfer_fee_rate" label="过户费率">
            <InputNumber
              style={{ width: '100%' }}
              min={0}
              max={0.01}
              step={0.00001}
            />
          </Form.Item>
          <Form.Item name="effective_from" label="生效日">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
