import { useState } from 'react';
import {
  Button,
  Popconfirm,
  Switch,
  Table,
  Tag,
  Tooltip,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';

import type { TaskResponse, TaskRunResponse } from '../../../api/types';
import { useTasksQuery, useTaskRunsQuery } from '../useTaskQueries';
import {
  usePauseTaskMutation,
  useResumeTaskMutation,
  useTriggerTaskMutation,
  useCancelTaskRunMutation,
  useRetryTaskRunMutation,
} from '../useTaskMutations';
import QueryBoundary from '../../../components/QueryBoundary';
import { defaultPagination } from '../../../lib/pagination';

const statusIconMap: Record<string, React.ReactNode> = {
  success: <CheckCircleOutlined />,
  failed: <ExclamationCircleOutlined />,
  running: <SyncOutlined spin />,
  queued: <SyncOutlined spin />,
  cancelled: <PauseCircleOutlined />,
  paused: <PauseCircleOutlined />,
};

const statusColorMap: Record<string, string> = {
  success: 'success',
  failed: 'error',
  running: 'processing',
  queued: 'processing',
  cancelled: 'default',
  paused: 'warning',
};

function formatDuration(ms: number | null): string {
  if (ms == null) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTime(t: string | null): string {
  if (!t) return '-';
  return dayjs(t).format('YYYY-MM-DD HH:mm:ss');
}

export default function TaskListTab() {
  const tasksQ = useTasksQuery();
  const runsQ = useTaskRunsQuery({ limit: 100 });
  const tasks = tasksQ.data ?? [];
  const runs = runsQ.data ?? [];

  const triggerM = useTriggerTaskMutation();
  const pauseM = usePauseTaskMutation();
  const resumeM = useResumeTaskMutation();
  const cancelM = useCancelTaskRunMutation();
  const retryM = useRetryTaskRunMutation();

  const [/* selectedTaskId */] = useState<string | null>(null);
  /* setSelectedTaskId unused — kept for future detail modal */

  const taskColumns: ColumnsType<TaskResponse> = [
    {
      title: '任务 ID',
      dataIndex: 'task_id',
      width: 200,
      render: (v: string) => (
        <code style={{ fontSize: 'var(--fs-sm)' }}>{v}</code>
      ),
    },
    {
      title: '类型',
      dataIndex: 'type',
      width: 80,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: '触发',
      dataIndex: 'trigger_type',
      width: 80,
      render: (v: string) => (
        <Tag color="blue">{v === 'cron' ? '定时' : v}</Tag>
      ),
    },
    {
      title: '调度规则',
      dataIndex: 'cron_expr',
      width: 160,
      render: (cron: string | null) =>
        cron ? <code>{cron}</code> : <span style={{ color: 'var(--gray-400)' }}>-</span>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 80,
      render: (s: string) => (
        <Tag
          color={
            s === 'active'
              ? 'success'
              : s === 'paused'
                ? 'warning'
                : 'default'
          }
        >
          {s === 'active' ? '启用' : s === 'paused' ? '暂停' : s}
        </Tag>
      ),
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      width: 70,
      render: (enabled: boolean, record: TaskResponse) => (
        <Switch
          size="small"
          checked={enabled}
          onChange={(v) => {
            if (v) {
              resumeM.mutate(record.task_id);
            } else {
              pauseM.mutate(record.task_id);
            }
          }}
        />
      ),
    },
    {
      title: '超时(s)',
      dataIndex: 'timeout_seconds',
      width: 80,
      render: (v: number | null) => (
        <span className="num">{v ?? '-'}</span>
      ),
    },
    {
      title: '上次执行',
      width: 200,
      render: (_: unknown, record: TaskResponse) => (
        <span>
          {record.last_run_status && (
            <Tag
              icon={statusIconMap[record.last_run_status]}
              color={statusColorMap[record.last_run_status]}
              style={{ marginRight: 4 }}
            >
              {record.last_run_status}
            </Tag>
          )}
          <span
            className="num"
            style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-secondary)' }}
          >
            {formatTime(record.last_run_at)}
          </span>
          {record.last_duration_ms != null && (
            <span
              style={{
                color: 'var(--gray-400)',
                fontSize: 'var(--fs-xs)',
                marginLeft: 4,
              }}
            >
              (<span className="num">{formatDuration(record.last_duration_ms)}</span>)
            </span>
          )}
        </span>
      ),
    },
    {
      title: '依赖',
      dataIndex: 'depends_on',
      width: 120,
      render: (deps: string[] | null) =>
        deps && deps.length > 0 ? (
          <Tooltip title={deps.join(', ')}>
            <Tag color="orange">{deps.length} 个</Tag>
          </Tooltip>
        ) : (
          <span style={{ color: 'var(--gray-400)' }}>-</span>
        ),
    },
    {
      title: '操作',
      width: 150,
      render: (_: unknown, record: TaskResponse) => (
        <>
          <Popconfirm
            title={`确认手动执行 ${record.task_id}?`}
            onConfirm={() => triggerM.mutate(record.task_id)}
          >
            <Button
              type="link"
              size="small"
              icon={<PlayCircleOutlined />}
              loading={triggerM.isPending}
            >
              执行
            </Button>
          </Popconfirm>
          {record.enabled ? (
            <Button
              type="link"
              size="small"
              icon={<PauseCircleOutlined />}
              onClick={() => pauseM.mutate(record.task_id)}
            >
              暂停
            </Button>
          ) : (
            <Button
              type="link"
              size="small"
              icon={<PlayCircleOutlined />}
              onClick={() => resumeM.mutate(record.task_id)}
            >
              恢复
            </Button>
          )}
        </>
      ),
    },
  ];

  const runColumns: ColumnsType<TaskRunResponse> = [
    {
      title: '运行 ID',
      dataIndex: 'id',
      width: 80,
      render: (v: number) => <span className="num">{v}</span>,
    },
    {
      title: '任务',
      dataIndex: 'task_id',
      width: 180,
      render: (v: string) => (
        <code style={{ fontSize: 'var(--fs-sm)' }}>{v}</code>
      ),
      filters: [...new Set(runs.map((r) => r.task_id))].map((j) => ({
        text: j,
        value: j,
      })),
      onFilter: (value, record) => record.task_id === value,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (s: string) => (
        <Tag
          icon={statusIconMap[s]}
          color={statusColorMap[s] || 'default'}
        >
          {s}
        </Tag>
      ),
    },
    {
      title: '进度',
      dataIndex: 'progress',
      width: 80,
      render: (p: number) => (
        <span className="num">{(p * 100).toFixed(0)}%</span>
      ),
    },
    {
      title: '开始',
      dataIndex: 'started_at',
      width: 170,
      render: (v: string | null) => (
        <span className="num" style={{ fontSize: 'var(--fs-xs)' }}>
          {formatTime(v)}
        </span>
      ),
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      width: 90,
      render: (v: number | null) => (
        <span className="num">{formatDuration(v)}</span>
      ),
    },
    {
      title: '触发方式',
      dataIndex: 'triggered_by',
      width: 90,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: '重试',
      dataIndex: 'retry_count',
      width: 80,
      render: (_: unknown, record: TaskRunResponse) =>
        record.max_retries > 0 ? (
          <span className="num">
            {record.retry_count}/{record.max_retries}
          </span>
        ) : (
          '-'
        ),
    },
    {
      title: '错误',
      dataIndex: 'last_error',
      ellipsis: true,
      width: 200,
      render: (v: string | null) =>
        v ? (
          <Tooltip title={v}>
            <span style={{ color: 'var(--red-600)', fontSize: 'var(--fs-xs)' }}>
              {v.slice(0, 60)}
            </span>
          </Tooltip>
        ) : (
          '-'
        ),
    },
    {
      title: '操作',
      width: 100,
      render: (_: unknown, record: TaskRunResponse) => (
        <>
          {record.status === 'queued' && (
            <Popconfirm
              title="确认取消?"
              onConfirm={() => cancelM.mutate(record.id)}
            >
              <Button type="link" size="small" danger>
                取消
              </Button>
            </Popconfirm>
          )}
          {record.status === 'failed' && (
            <Popconfirm
              title="确认重试?"
              onConfirm={() => retryM.mutate(record.id)}
            >
              <Button type="link" size="small">
                重试
              </Button>
            </Popconfirm>
          )}
        </>
      ),
    },
  ];

  return (
    <div>
      {/* Task Definition Table */}
      <h4 style={{ marginBottom: 8 }}>Task 定义</h4>
      <QueryBoundary query={tasksQ}>
        {() => (
          <Table<TaskResponse>
            rowKey="task_id"
            columns={taskColumns}
            dataSource={tasks}
            loading={tasksQ.isFetching && !tasksQ.data}
            pagination={false}
            size="middle"
            style={{ marginBottom: 24 }}
          />
        )}
      </QueryBoundary>

      {/* Task Run History */}
      <h4 style={{ marginBottom: 8 }}>运行历史</h4>
      <QueryBoundary query={runsQ}>
        {() => (
          <Table<TaskRunResponse>
            rowKey="id"
            columns={runColumns}
            dataSource={runs}
            loading={runsQ.isFetching && !runsQ.data}
            pagination={{ ...defaultPagination, defaultPageSize: 50 }}
            size="middle"
          />
        )}
      </QueryBoundary>
    </div>
  );
}
