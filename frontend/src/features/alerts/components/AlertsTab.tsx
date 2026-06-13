import { useState, useMemo } from 'react';
import {
  Button,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { CheckCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';

import QueryBoundary from '../../../components/QueryBoundary';
import { FilterBar, EmptyState } from '../../../components/primitives';
import { defaultPagination } from '../../../lib/pagination';
import { useAlertsQuery } from '../useAlertQueries';
import {
  useResolveAlertMutation,
  useBulkResolveAlertsMutation,
} from '../useAlertMutations';
import type {
  SystemAlert,
  SystemAlertCategory,
  SystemAlertSeverity,
} from '../../../api/types';

const { Text } = Typography;

const SEVERITY_META: Record<SystemAlertSeverity, { color: string; label: string }> = {
  critical: { color: 'red', label: '严重' },
  warning: { color: 'orange', label: '警告' },
  info: { color: 'blue', label: '提示' },
};

const CATEGORY_LABEL: Record<SystemAlertCategory, string> = {
  data: '数据',
  scheduler: '调度',
  api: 'API',
  db: '数据库',
  token: 'Token',
};

type SeverityFilter = 'all' | SystemAlertSeverity;
type CategoryFilter = 'all' | SystemAlertCategory;

export default function AlertsTab() {
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all');
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>('all');
  const [selectedIds, setSelectedIds] = useState<number[]>([]);

  const queryFilter = useMemo(
    () => ({
      unresolved_only: true,
      severity: severityFilter === 'all' ? undefined : severityFilter,
      category: categoryFilter === 'all' ? undefined : categoryFilter,
      limit: 500,
    }),
    [severityFilter, categoryFilter],
  );

  const q = useAlertsQuery(queryFilter);
  const resolveM = useResolveAlertMutation();
  const bulkResolveM = useBulkResolveAlertsMutation();

  const handleReset = () => {
    setSeverityFilter('all');
    setCategoryFilter('all');
  };

  const handleBulkResolve = async () => {
    if (selectedIds.length === 0) return;
    await bulkResolveM.mutateAsync(selectedIds);
    setSelectedIds([]);
  };

  const columns: ColumnsType<SystemAlert> = [
    {
      title: '级别',
      dataIndex: 'severity',
      width: 80,
      render: (s: SystemAlertSeverity) => (
        <Tag color={SEVERITY_META[s].color}>{SEVERITY_META[s].label}</Tag>
      ),
    },
    {
      title: '类别',
      dataIndex: 'category',
      width: 90,
      render: (c: SystemAlertCategory) => CATEGORY_LABEL[c] ?? c,
    },
    {
      title: '内容',
      dataIndex: 'message',
      ellipsis: { showTitle: false },
      render: (msg: string, record) => (
        <Tooltip
          title={record.detail_json ? JSON.stringify(record.detail_json, null, 2) : msg}
        >
          <span>{msg}</span>
        </Tooltip>
      ),
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 160,
      render: (ts: string) => (
        <span
          className="num"
          style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}
        >
          {dayjs(ts).format('MM-DD HH:mm:ss')}
        </span>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 110,
      render: (_, record) => (
        <Popconfirm
          title="标记为已解决？"
          onConfirm={() => resolveM.mutate(record.id)}
          okText="确认"
          cancelText="取消"
        >
          <Button
            size="small"
            type="link"
            icon={<CheckCircleOutlined />}
            loading={resolveM.isPending}
          >
            解决
          </Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <div>
      <FilterBar
        onReset={handleReset}
        actions={
          <Button
            size="small"
            icon={<ReloadOutlined />}
            onClick={() => q.refetch()}
            loading={q.isFetching}
          >
            刷新
          </Button>
        }
      >
        <Space size={12} wrap>
          <Space size={4}>
            <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}>
              级别
            </span>
            <Select
              size="small"
              value={severityFilter}
              onChange={(v) => setSeverityFilter(v as SeverityFilter)}
              style={{ width: 110 }}
              options={[
                { value: 'all', label: '全部' },
                { value: 'critical', label: '严重' },
                { value: 'warning', label: '警告' },
                { value: 'info', label: '提示' },
              ]}
            />
          </Space>
          <Space size={4}>
            <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}>
              类别
            </span>
            <Select
              size="small"
              value={categoryFilter}
              onChange={(v) => setCategoryFilter(v as CategoryFilter)}
              style={{ width: 110 }}
              options={[
                { value: 'all', label: '全部' },
                ...Object.entries(CATEGORY_LABEL).map(([value, label]) => ({
                  value,
                  label,
                })),
              ]}
            />
          </Space>
        </Space>
      </FilterBar>

      {selectedIds.length > 0 && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: 'var(--sp-2) var(--sp-4)',
            background: 'var(--primary-100)',
            borderRadius: 'var(--radius-md)',
            marginBottom: 'var(--sp-3)',
          }}
        >
          <Text style={{ color: 'var(--primary-700)' }}>
            已选 <span className="num">{selectedIds.length}</span> 条
          </Text>
          <Popconfirm
            title={`确认批量解决 ${selectedIds.length} 条告警？`}
            onConfirm={handleBulkResolve}
            okText="确认"
            cancelText="取消"
          >
            <Button
              size="small"
              type="primary"
              icon={<CheckCircleOutlined />}
              loading={bulkResolveM.isPending}
            >
              批量解决
            </Button>
          </Popconfirm>
        </div>
      )}

      <QueryBoundary
        query={q}
        isEmpty={(data) => data.length === 0}
        emptyRender={
          <EmptyState variant="quiet" title="当前筛选条件下无未解决告警" />
        }
      >
        {(data) => (
          <Table<SystemAlert>
            size="small"
            rowKey="id"
            columns={columns}
            dataSource={data}
            rowSelection={{
              selectedRowKeys: selectedIds,
              onChange: (keys) => setSelectedIds(keys.map(Number)),
            }}
            pagination={{ ...defaultPagination, defaultPageSize: 50 }}
          />
        )}
      </QueryBoundary>
    </div>
  );
}
