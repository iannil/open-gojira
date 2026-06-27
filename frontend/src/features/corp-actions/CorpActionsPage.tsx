import { Table, Tag, Typography, Button, Popconfirm, Select, message } from 'antd';
import { useState } from 'react';
import {
  BankOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import {
  listCorpActions,
  processCorpAction,
  processPendingCorpActions,
} from '../../api/client';
import type { CorpAction, CorpActionType } from '../../api/types';
import { PageHeader, FilterBar } from '../../components/primitives';
import PageSection from '../../components/primitives/PageSection';
import QueryBoundary from '../../components/QueryBoundary';

const { Text } = Typography;

const ACTION_TYPE_LABELS: Record<string, string> = {
  cash_dividend: '现金分红',
  stock_dividend: '送股',
  capitalization: '转增',
  rights_issue: '配股',
  delist: '退市',
  merger: '合并',
  code_change: '代码变更',
};

const ACTION_TYPE_COLORS: Record<string, string> = {
  cash_dividend: 'green',
  stock_dividend: 'blue',
  capitalization: 'cyan',
  rights_issue: 'purple',
  delist: 'red',
  merger: 'orange',
  code_change: 'geekblue',
};

function fmtDt(s: string | null): string {
  if (!s) return '—';
  return new Date(s).toLocaleString('zh-CN', { hour12: false });
}

const COLUMNS: ColumnsType<CorpAction> = [
  { title: 'ID', dataIndex: 'id', width: 60 },
  { title: '股票', dataIndex: 'stock_code', width: 90 },
  { title: '除权日', dataIndex: 'ex_date', width: 100 },
  {
    title: '类型',
    dataIndex: 'action_type',
    width: 100,
    render: (t: CorpActionType) => (
      <Tag color={ACTION_TYPE_COLORS[t] ?? 'default'}>
        {ACTION_TYPE_LABELS[t] ?? t}
      </Tag>
    ),
  },
  {
    title: '状态',
    dataIndex: 'processed_at',
    width: 80,
    render: (v: string | null) => v
      ? <Tag color="success">已处理</Tag>
      : <Tag color="warning">待处理</Tag>,
  },
  {
    title: '参数',
    dataIndex: 'params_json',
    width: 200,
    ellipsis: true,
    render: (p: Record<string, unknown>) =>
      <Text code style={{ fontSize: 11 }}>{JSON.stringify(p)}</Text>,
  },
  {
    title: '来源',
    dataIndex: 'source',
    width: 80,
  },
  {
    title: '处理时间',
    dataIndex: 'processed_at',
    width: 150,
    render: (v: string | null) => v ? fmtDt(v) : '—',
  },
];

export default function CorpActionsPage() {
  const queryClient = useQueryClient();
  const [filterStatus, setFilterStatus] = useState<string | undefined>();
  const [filterType, setFilterType] = useState<string | undefined>();

  const listQ = useQuery({
    queryKey: ['corp-actions', { status: filterStatus, action_type: filterType }],
    queryFn: () => listCorpActions({ status: filterStatus as any, action_type: filterType as any, limit: 200 }),
  });

  const processM = useMutation({
    mutationFn: processCorpAction,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['corp-actions'] }),
    onError: (err) => message.error(`处理失败: ${err instanceof Error ? err.message : '未知错误'}`),
  });

  const batchProcessM = useMutation({
    mutationFn: processPendingCorpActions,
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['corp-actions'] });
      message.success(`已处理 ${result.processed_count} 条`);
    },
    onError: (err) => message.error(`批量处理失败: ${err instanceof Error ? err.message : '未知错误'}`),
  });

  return (
    <div>
      <PageHeader
        title="公司行动"
        enLabel="Corp Actions"
        purpose="分红、送股、配股、代码变更等公司行动管理 — 自动同步、手动处理。"
        actions={
          <Popconfirm
            title="批量处理所有待处理公司行动？"
            onConfirm={() => batchProcessM.mutate()}
            okText="确认处理"
            cancelText="取消"
          >
            <Button icon={<PlayCircleOutlined />} loading={batchProcessM.isPending}>
              批量处理待办
            </Button>
          </Popconfirm>
        }
      />

      <FilterBar onReset={() => { setFilterStatus(undefined); setFilterType(undefined); }}>
        <Select
          placeholder="状态"
          allowClear
          style={{ width: 120 }}
          value={filterStatus}
          onChange={setFilterStatus}
          options={[
            { value: 'pending', label: '待处理' },
            { value: 'processed', label: '已处理' },
          ]}
        />
        <Select
          placeholder="类型"
          allowClear
          style={{ width: 140 }}
          value={filterType}
          onChange={setFilterType}
          options={Object.entries(ACTION_TYPE_LABELS).map(([v, l]) => ({ value: v, label: l }))}
        />
      </FilterBar>

      <PageSection
        title={<><BankOutlined /> 公司行动列表</>}
        extra={<Text type="secondary">{listQ.data?.length ?? 0} 条</Text>}
      >
        <QueryBoundary
          query={listQ}
          isEmpty={(d) => d.length === 0}
          emptyRender={<Text type="secondary">暂无公司行动记录。</Text>}
        >
          {() => {
            const actions = listQ.data!;

            const actionCols: ColumnsType<CorpAction> = [
              ...COLUMNS,
              {
                title: '操作',
                width: 80,
                render: (_, r) =>
                  !r.processed_at ? (
                    <Popconfirm
                      title="确认处理此公司行动？"
                      onConfirm={() => processM.mutate(r.id)}
                      okText="确认"
                      cancelText="取消"
                    >
                      <Button size="small" type="link" loading={processM.isPending}>
                        处理
                      </Button>
                    </Popconfirm>
                  ) : (
                    <Tag color="default">已完成</Tag>
                  ),
              },
            ];

            return (
              <Table<CorpAction>
                columns={actionCols}
                dataSource={actions}
                rowKey="id"
                size="small"
                pagination={{ pageSize: 20, size: 'small' }}
                scroll={{ x: 1000 }}
              />
            );
          }}
        </QueryBoundary>
      </PageSection>
    </div>
  );
}
