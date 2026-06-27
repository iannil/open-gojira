import { useState } from 'react';
import { Table, Typography, Select, InputNumber } from 'antd';
import { HistoryOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useQuery } from '@tanstack/react-query';

import { fetchAuditLog } from '../../api/client';
import type { AuditLogEntry } from '../../api/types';
import { PageHeader, FilterBar } from '../../components/primitives';
import PageSection from '../../components/primitives/PageSection';
import QueryBoundary from '../../components/QueryBoundary';

const { Text } = Typography;

function fmtDt(s: string | null): string {
  if (!s) return '—';
  return new Date(s).toLocaleString('zh-CN', { hour12: false });
}

const COLUMNS: ColumnsType<AuditLogEntry> = [
  { title: 'ID', dataIndex: 'id', width: 60 },
  {
    title: '时间',
    dataIndex: 'created_at',
    width: 160,
    render: (v: string | null) => (
      <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}>
        {fmtDt(v)}
      </span>
    ),
  },
  { title: '类型', dataIndex: 'entity_type', width: 100 },
  { title: '事件', dataIndex: 'event', width: 120 },
  { title: '股票', dataIndex: 'stock_code', width: 80 },
  { title: '摘要', dataIndex: 'summary', ellipsis: true },
  {
    title: '数据',
    dataIndex: 'payload',
    width: 200,
    ellipsis: true,
    render: (p: Record<string, unknown> | null) =>
      p ? <Text code style={{ fontSize: 11 }}>{JSON.stringify(p)}</Text> : null,
  },
];

export default function AuditLogPage() {
  const [entityType, setEntityType] = useState<string | undefined>();
  const [event, setEvent] = useState<string | undefined>();
  const [stockCode, setStockCode] = useState<string | undefined>();
  const [limit, setLimit] = useState(100);

  const q = useQuery({
    queryKey: ['audit-log', { entity_type: entityType, event, stock_code: stockCode, limit }],
    queryFn: () => fetchAuditLog({ entity_type: entityType, event, stock_code: stockCode, limit }),
    refetchInterval: 30_000,
  });

  return (
    <div>
      <PageHeader
        title="审计日志"
        enLabel="Audit Log"
        purpose="全链路黑匣子：记录所有关键操作（交易、Draft、Pipeline、LLM 调用）的不可变审计轨迹。"
      />

      <FilterBar onReset={() => { setEntityType(undefined); setEvent(undefined); setStockCode(undefined); setLimit(100); }}>
        <Select
          placeholder="实体类型"
          allowClear
          style={{ width: 140 }}
          value={entityType}
          onChange={setEntityType}
          options={[
            { value: 'trade', label: 'trade' },
            { value: 'draft', label: 'draft' },
            { value: 'pipeline', label: 'pipeline' },
            { value: 'llm_call', label: 'llm_call' },
            { value: 'stock', label: 'stock' },
            { value: 'system', label: 'system' },
          ]}
        />
        <Select
          placeholder="事件"
          allowClear
          style={{ width: 140 }}
          value={event}
          onChange={setEvent}
          options={[
            { value: 'created', label: 'created' },
            { value: 'updated', label: 'updated' },
            { value: 'deleted', label: 'deleted' },
            { value: 'executed', label: 'executed' },
            { value: 'cancelled', label: 'cancelled' },
            { value: 'processed', label: 'processed' },
          ]}
        />
        <InputNumber
          placeholder="股票代码"
          style={{ width: 120 }}
          value={stockCode}
          onChange={(v) => setStockCode(v ? String(v) : undefined)}
        />
        <InputNumber
          placeholder="条数"
          min={10}
          max={500}
          style={{ width: 100 }}
          value={limit}
          onChange={(v) => setLimit(v ?? 100)}
        />
      </FilterBar>

      <PageSection
        title={<><HistoryOutlined /> 日志记录</>}
        extra={<Text type="secondary">{q.data?.length ?? 0} 条</Text>}
      >
        <QueryBoundary
          query={q}
          isEmpty={(d) => d.length === 0}
          emptyRender={<Text type="secondary">暂无匹配的审计日志记录。</Text>}
        >
          {() => (
            <Table<AuditLogEntry>
              columns={COLUMNS}
              dataSource={q.data!}
              rowKey="id"
              size="small"
              pagination={{ pageSize: 30, size: 'small' }}
              scroll={{ x: 900 }}
            />
          )}
        </QueryBoundary>
      </PageSection>
    </div>
  );
}
