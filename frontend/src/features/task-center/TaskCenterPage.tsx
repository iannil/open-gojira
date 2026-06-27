import { useState } from 'react';
import {
  Button,
  Card,
  Col,
  Popconfirm,
  Row,
  Space,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SyncOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { PageHeader } from '../../components/primitives';
import QueryBoundary from '../../components/QueryBoundary';
import { defaultPagination } from '../../lib/pagination';
import {
  listTasks,
  listTaskRuns,
  taskHealth,
  triggerTask,
  pauseTask,
  resumeTask,
  cancelTaskRun,
  retryTaskRun,
} from '../../api/client';
import type {
  TaskResponse,
  TaskRunResponse,
} from '../../api/types';

const { Text } = Typography;

// ── Helpers ──────────────────────────────────────────────────────────

function formatDuration(ms: number | null): string {
  if (ms == null) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTime(t: string | null): string {
  if (!t) return '-';
  return dayjs(t).format('YYYY-MM-DD HH:mm:ss');
}

const statusIconMap: Record<string, React.ReactNode> = {
  success: <CheckCircleOutlined />,
  failed: <ExclamationCircleOutlined />,
  running: <SyncOutlined spin />,
  queued: <ClockCircleOutlined />,
  cancelled: <CloseCircleOutlined />,
};

const statusColorMap: Record<string, string> = {
  success: 'success',
  failed: 'error',
  running: 'processing',
  queued: 'processing',
  cancelled: 'default',
};

// ── Page Component ───────────────────────────────────────────────────

export default function TaskCenterPage() {
  const queryClient = useQueryClient();

  // Data queries
  const healthQ = useQuery({
    queryKey: ['task-center', 'health'],
    queryFn: taskHealth,
    refetchInterval: 10_000,
  });
  const tasksQ = useQuery({
    queryKey: ['task-center', 'tasks'],
    queryFn: listTasks,
    refetchInterval: 15_000,
  });
  const runsQ = useQuery({
    queryKey: ['task-center', 'runs'],
    queryFn: () => listTaskRuns({ limit: 200 }),
    refetchInterval: 5_000,
  });

  // Action state
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const health = healthQ.data;
  const tasks = tasksQ.data ?? [];
  const runs = runsQ.data ?? [];

  const doAction = async (
    action: string,
    fn: () => Promise<unknown>,
    taskId: string,
  ) => {
    setActionLoading(`${action}-${taskId}`);
    try {
      await fn();
      queryClient.invalidateQueries({ queryKey: ['task-center'] });
    } catch {
      // Error handled by API client
    } finally {
      setActionLoading(null);
    }
  };

  // ── Stats Cards ─────────────────────────────────────────────────

  const runningCount = runs.filter((r) => r.status === 'running').length;
  const queuedCount = runs.filter((r) => r.status === 'queued').length;
  const failed24h = runs.filter(
    (r) =>
      r.status === 'failed' &&
      r.created_at &&
      dayjs().diff(dayjs(r.created_at), 'hour') < 24,
  ).length;

  // ── Task Columns ───────────────────────────────────────────────

  const taskColumns: ColumnsType<TaskResponse> = [
    {
      title: '任务 ID',
      dataIndex: 'task_id',
      width: 180,
      fixed: 'left',
      render: (v: string) => (
        <code style={{ fontSize: 'var(--fs-sm)' }}>{v}</code>
      ),
    },
    {
      title: '类型',
      dataIndex: 'type',
      width: 60,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: '触发',
      dataIndex: 'trigger_type',
      width: 60,
      render: (v: string) => (
        <Tag color="blue">{v === 'cron' ? '定时' : v}</Tag>
      ),
    },
    {
      title: '调度规则',
      dataIndex: 'cron_expr',
      width: 130,
      render: (cron: string | null) =>
        cron ? (
          <code style={{ fontSize: 'var(--fs-xs)' }}>{cron}</code>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 70,
      render: (s: string) => (
        <Tag
          color={
            s === 'active' ? 'success' : s === 'paused' ? 'warning' : 'default'
          }
        >
          {s === 'active' ? '启用' : s === 'paused' ? '暂停' : s}
        </Tag>
      ),
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      width: 60,
      render: (enabled: boolean, record: TaskResponse) => {
        const key = `toggle-${record.task_id}`;
        return (
          <Switch
            size="small"
            checked={enabled}
            loading={actionLoading === key}
            onChange={(v) =>
              doAction(
                'toggle',
                () => (v ? resumeTask(record.task_id) : pauseTask(record.task_id)),
                record.task_id,
              )
            }
          />
        );
      },
    },
    {
      title: '超时',
      dataIndex: 'timeout_seconds',
      width: 60,
      render: (v: number | null) => (
        <Text className="num">{v ? `${v}s` : '-'}</Text>
      ),
    },

    {
      title: '上次执行',
      width: 200,
      render: (_: unknown, record: TaskResponse) => (
        <Space size={4}>
          {record.last_run_status && (
            <Tag
              icon={statusIconMap[record.last_run_status]}
              color={statusColorMap[record.last_run_status]}
              style={{ marginRight: 0 }}
            >
              {record.last_run_status}
            </Tag>
          )}
          <Text
            className="num"
            type="secondary"
            style={{ fontSize: 'var(--fs-xs)' }}
          >
            {formatTime(record.last_run_at)}
          </Text>
          {record.last_duration_ms != null && (
            <Text type="secondary" style={{ fontSize: 'var(--fs-xs)' }}>
              ({formatDuration(record.last_duration_ms)})
            </Text>
          )}
        </Space>
      ),
    },
    {
      title: '依赖',
      dataIndex: 'depends_on',
      width: 80,
      render: (deps: string[] | null) =>
        deps && deps.length > 0 ? (
          <Tooltip title={deps.join(', ')}>
            <Tag color="orange">{deps.length}</Tag>
          </Tooltip>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: '操作',
      width: 140,
      fixed: 'right',
      render: (_: unknown, record: TaskResponse) => {
        const triggerKey = `trigger-${record.task_id}`;
        return (
          <Space size={0}>
            <Popconfirm
              title={`确认执行 ${record.task_id}?`}
              onConfirm={() =>
                doAction('trigger', () => triggerTask(record.task_id), record.task_id)
              }
            >
              <Button
                type="link"
                size="small"
                icon={<PlayCircleOutlined />}
                loading={actionLoading === triggerKey}
              >
                执行
              </Button>
            </Popconfirm>
            {record.enabled ? (
              <Button
                type="link"
                size="small"
                icon={<PauseCircleOutlined />}
                loading={actionLoading === `toggle-${record.task_id}`}
                onClick={() =>
                  doAction(
                    'pause',
                    () => pauseTask(record.task_id),
                    record.task_id,
                  )
                }
              >
                暂停
              </Button>
            ) : (
              <Button
                type="link"
                size="small"
                icon={<PlayCircleOutlined />}
                loading={actionLoading === `toggle-${record.task_id}`}
                onClick={() =>
                  doAction(
                    'resume',
                    () => resumeTask(record.task_id),
                    record.task_id,
                  )
                }
              >
                恢复
              </Button>
            )}
          </Space>
        );
      },
    },
  ];

  // ── Run Columns ─────────────────────────────────────────────────

  const runColumns: ColumnsType<TaskRunResponse> = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 60,
      render: (v: number) => <Text className="num">{v}</Text>,
    },
    {
      title: '任务',
      dataIndex: 'task_id',
      width: 160,
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
      width: 90,
      render: (s: string) => (
        <Tag icon={statusIconMap[s]} color={statusColorMap[s] || 'default'}>
          {s}
        </Tag>
      ),
    },
    {
      title: '进度',
      dataIndex: 'progress',
      width: 70,
      render: (p: number) => (
        <Text className="num">{(p * 100).toFixed(0)}%</Text>
      ),
    },
    {
      title: '开始',
      dataIndex: 'started_at',
      width: 160,
      render: (v: string | null) => (
        <Text className="num" style={{ fontSize: 'var(--fs-xs)' }}>
          {formatTime(v)}
        </Text>
      ),
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      width: 80,
      render: (v: number | null) => (
        <Text className="num">{formatDuration(v)}</Text>
      ),
    },
    {
      title: '触发',
      dataIndex: 'triggered_by',
      width: 70,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: '重试',
      dataIndex: 'retry_count',
      width: 60,
      render: (_: unknown, record: TaskRunResponse) =>
        record.max_retries > 0 ? (
          <Text className="num">
            {record.retry_count}/{record.max_retries}
          </Text>
        ) : (
          '-'
        ),
    },
    {
      title: '错误',
      dataIndex: 'last_error',
      ellipsis: true,
      width: 180,
      render: (v: string | null) =>
        v ? (
          <Tooltip title={v}>
            <Text style={{ color: 'var(--red-600)', fontSize: 'var(--fs-xs)' }}>
              {v.slice(0, 60)}
            </Text>
          </Tooltip>
        ) : (
          '-'
        ),
    },
    {
      title: '操作',
      width: 80,
      render: (_: unknown, record: TaskRunResponse) => (
        <Space size={0}>
          {record.status === 'queued' && (
            <Popconfirm
              title="确认取消?"
              onConfirm={() =>
                doAction('cancel', () => cancelTaskRun(record.id), String(record.id))
              }
            >
              <Button type="link" size="small" danger>
                取消
              </Button>
            </Popconfirm>
          )}
          {record.status === 'failed' && (
            <Popconfirm
              title="确认重试?"
              onConfirm={() =>
                doAction('retry', () => retryTaskRun(record.id), String(record.id))
              }
            >
              <Button type="link" size="small">
                重试
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  // ── Render ──────────────────────────────────────────────────────

  return (
    <div>
      <PageHeader
        title="任务管理"
        enLabel="Task Center"
        purpose={`统一任务调度中心 — ${tasks.length} 个任务，${tasks.filter((t) => t.enabled).length} 个启用`}
        flow={[{ label: '任务管理' }]}
      />

      {/* ── Health Cards ── */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="Engine 状态"
              value={health?.engine_running ? '运行中' : '已停止'}
              valueStyle={{
                color: health?.engine_running
                  ? 'var(--green-600)'
                  : 'var(--red-600)',
              }}
              prefix={
                health?.engine_running ? (
                  <SyncOutlined spin />
                ) : (
                  <CloseCircleOutlined />
                )
              }
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="运行中 / 排队中"
              value={`${runningCount} / ${queuedCount}`}
              prefix={<ThunderboltOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="24h 内失败"
              value={failed24h}
              valueStyle={{
                color: failed24h > 0 ? 'var(--red-600)' : undefined,
              }}
              prefix={<ExclamationCircleOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="运行时长"
              value={
                health?.uptime_seconds != null
                  ? formatDuration(health.uptime_seconds * 1000)
                  : '-'
              }
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Tabs
        type="card"
        items={[
          {
            key: 'runs',
            label: (
              <span>
                <SyncOutlined /> 运行历史
              </span>
            ),
            children: (
              <Card size="small">
                <QueryBoundary query={runsQ}>
                  {() => (
                    <Table<TaskRunResponse>
                      rowKey="id"
                      columns={runColumns}
                      dataSource={runs}
                      loading={runsQ.isFetching && !runsQ.data}
                      pagination={{ ...defaultPagination, defaultPageSize: 50 }}
                      size="small"
                      scroll={{ x: 1100 }}
                    />
                  )}
                </QueryBoundary>
              </Card>
            ),
          },
          {
            key: 'tasks',
            label: (
              <span>
                <ThunderboltOutlined /> Task 定义
              </span>
            ),
            children: (
              <Card
                size="small"
                extra={
                  <Button
                    size="small"
                    icon={<ReloadOutlined />}
                    onClick={() => queryClient.invalidateQueries({ queryKey: ['task-center'] })}
                  >
                    刷新
                  </Button>
                }
              >
                <QueryBoundary query={tasksQ}>
                  {() => (
                    <Table<TaskResponse>
                      rowKey="task_id"
                      columns={taskColumns}
                      dataSource={tasks}
                      loading={tasksQ.isFetching && !tasksQ.data}
                      pagination={false}
                      size="small"
                      scroll={{ x: 1200 }}
                    />
                  )}
                </QueryBoundary>
              </Card>
            ),
          },
        ]}
      />
    </div>
  );
}
