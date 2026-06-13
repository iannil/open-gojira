import { useState } from 'react';
import { Button, Input, Popconfirm, Switch, Table, Tabs, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  PlayCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';

import { PageHeader } from '../../components/primitives';
import QueryBoundary from '../../components/QueryBoundary';
import { defaultPagination } from '../../lib/pagination';
import { useJobExecutionsQuery, useSchedulerJobsQuery } from './useSchedulerQueries';
import {
  useTriggerSchedulerJobMutation,
  useUpdateSchedulerJobMutation,
} from './useSchedulerMutations';
import type { JobExecutionResponse, SchedulerJobResponse } from '../../api/types';

function formatDuration(ms: number | null): string {
  if (ms == null) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTime(t: string | null): string {
  if (!t) return '-';
  return dayjs(t).format('YYYY-MM-DD HH:mm:ss');
}

function parseCronHuman(cron: string): string {
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) return cron;
  const [min, hour, dom, mon, dow] = parts;

  const dowMap: Record<string, string> = {
    '0': '周日',
    '1': '周一',
    '2': '周二',
    '3': '周三',
    '4': '周四',
    '5': '周五',
    '6': '周六',
    '7': '周日',
    '1-5': '工作日',
  };

  const monMap: Record<string, string> = {
    '1': '1月',
    '2': '2月',
    '3': '3月',
    '4': '4月',
    '5': '5月',
    '6': '6月',
    '7': '7月',
    '8': '8月',
    '9': '9月',
    '10': '10月',
    '11': '11月',
    '12': '12月',
    '3,4,8,10': '季报月(3,4,8,10)',
    '1,4,7,10': '季初月(1,4,7,10)',
  };

  const timeStr = `${hour.padStart(2, '0')}:${min.padStart(2, '0')}`;

  if (dom === '*' && mon === '*') {
    if (dow !== '*') {
      return `${dowMap[dow] || `星期${dow}`} ${timeStr}`;
    }
    return `每天 ${timeStr}`;
  }

  if (dom !== '*' && dow === '*') {
    const monStr = mon !== '*' ? (monMap[mon] || `${mon}月`) : '';
    let domStr = dom;
    if (dom === '1') domStr = '每月1日';
    else if (dom === '5') domStr = '每月5日';
    else if (dom.includes('-')) domStr = `${dom}日`;
    return `${monStr} ${domStr} ${timeStr}`.trim();
  }

  return cron;
}

export default function SchedulerPage() {
  const [editingJob, setEditingJob] = useState<string | null>(null);
  const [editCron, setEditCron] = useState('');

  const jobsQ = useSchedulerJobsQuery();
  const execsQ = useJobExecutionsQuery(100);
  const updateM = useUpdateSchedulerJobMutation();
  const triggerM = useTriggerSchedulerJobMutation();

  const jobs = jobsQ.data ?? [];
  const executions = execsQ.data ?? [];
  const enabledCount = jobs.filter((j) => j.enabled).length;

  const handleCronSave = async (jobId: string) => {
    await updateM.mutateAsync(
      { jobId, payload: { cron_expr: editCron } },
      { onSuccess: () => setEditingJob(null) },
    );
  };

  const jobColumns: ColumnsType<SchedulerJobResponse> = [
    {
      title: '任务 ID',
      dataIndex: 'job_id',
      width: 200,
      render: (v: string) => (
        <code style={{ fontSize: 'var(--fs-sm)' }}>{v}</code>
      ),
    },
    { title: '描述', dataIndex: 'description', ellipsis: true },
    {
      title: '调度规则',
      dataIndex: 'cron_expr',
      width: 280,
      render: (cron: string, record: SchedulerJobResponse) => {
        if (editingJob === record.job_id) {
          return (
            <Input.Search
              size="small"
              value={editCron}
              onChange={(e) => setEditCron(e.target.value)}
              enterButton="保存"
              onSearch={() => handleCronSave(record.job_id)}
              onBlur={() => setEditingJob(null)}
              style={{ width: 240 }}
              placeholder="0 17 * * 1-5"
            />
          );
        }
        return (
          <span
            onClick={() => {
              setEditingJob(record.job_id);
              setEditCron(cron);
            }}
            style={{
              cursor: 'pointer',
              borderBottom: '1px dashed var(--gray-300)',
            }}
            title="点击编辑"
          >
            <code>{cron}</code>
            <span
              style={{
                color: 'var(--gray-400)',
                fontSize: 'var(--fs-xs)',
                marginLeft: 8,
              }}
            >
              ({parseCronHuman(cron)})
            </span>
          </span>
        );
      },
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      width: 90,
      render: (enabled: boolean, record: SchedulerJobResponse) => (
        <Switch
          size="small"
          checked={enabled}
          loading={updateM.isPending}
          onChange={(v) =>
            updateM.mutate({ jobId: record.job_id, payload: { enabled: v } })
          }
        />
      ),
    },
    {
      title: '上次执行',
      width: 200,
      render: (_: unknown, record: SchedulerJobResponse) => (
        <span>
          {record.last_run_status === 'success' && (
            <CheckCircleOutlined
              style={{ color: 'var(--green-600)', marginRight: 4 }}
            />
          )}
          {record.last_run_status === 'failed' && (
            <ExclamationCircleOutlined
              style={{ color: 'var(--red-600)', marginRight: 4 }}
            />
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
      title: '下次执行',
      dataIndex: 'next_run_time',
      width: 170,
      render: (v: string | null, record: SchedulerJobResponse) =>
        record.enabled ? (
          <span
            className="num"
            style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-secondary)' }}
          >
            {formatTime(v)}
          </span>
        ) : (
          <span style={{ color: 'var(--gray-400)' }}>-</span>
        ),
    },
    {
      title: '操作',
      width: 110,
      render: (_: unknown, record: SchedulerJobResponse) => (
        <Popconfirm
          title={`确认手动执行 ${record.job_id}?`}
          onConfirm={() => triggerM.mutate(record.job_id)}
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
      ),
    },
  ];

  const statusIconMap: Record<string, React.ReactNode> = {
    success: <CheckCircleOutlined />,
    failed: <ExclamationCircleOutlined />,
    running: <SyncOutlined spin />,
  };

  const execColumns: ColumnsType<JobExecutionResponse> = [
    {
      title: '任务',
      dataIndex: 'job_id',
      width: 180,
      render: (v: string) => (
        <code style={{ fontSize: 'var(--fs-sm)' }}>{v}</code>
      ),
      filters: [...new Set(executions.map((e) => e.job_id))].map((j) => ({
        text: j,
        value: j,
      })),
      onFilter: (value, record) => record.job_id === value,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (s: string) => (
        <Tag
          icon={statusIconMap[s]}
          color={
            s === 'success' ? 'success' : s === 'failed' ? 'error' : 'processing'
          }
        >
          {s === 'success' ? '成功' : s === 'failed' ? '失败' : '运行中'}
        </Tag>
      ),
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      width: 170,
      render: (v: string | null) => (
        <span
          className="num"
          style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-secondary)' }}
        >
          {formatTime(v)}
        </span>
      ),
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      width: 90,
      render: (v: number | null) => <span className="num">{formatDuration(v)}</span>,
    },
    {
      title: '结果',
      dataIndex: 'result_summary',
      ellipsis: true,
      render: (v: string | null) =>
        v ? (
          <span style={{ color: 'var(--gray-600)', fontSize: 'var(--fs-xs)' }}>
            {v.slice(0, 120)}
          </span>
        ) : (
          '-'
        ),
    },
    {
      title: '错误',
      dataIndex: 'error_message',
      ellipsis: true,
      render: (v: string | null) =>
        v ? (
          <span style={{ color: 'var(--red-600)', fontSize: 'var(--fs-xs)' }}>
            {v}
          </span>
        ) : (
          '-'
        ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="定时任务"
        enLabel="Scheduler"
        purpose={`后台 cron 调度。共 ${jobs.length} 个任务，${enabledCount} 个启用。可手动触发、修改 cron 表达式、查看执行历史。`}
        flow={[{ label: '定时任务' }]}
      />

      <Tabs
        defaultActiveKey="jobs"
        items={[
          {
            key: 'jobs',
            label: '任务管理',
            children: (
              <QueryBoundary query={jobsQ}>
                {() => (
                  <Table<SchedulerJobResponse>
                    rowKey="job_id"
                    columns={jobColumns}
                    dataSource={jobs}
                    loading={jobsQ.isFetching && !jobsQ.data}
                    pagination={false}
                    size="middle"
                  />
                )}
              </QueryBoundary>
            ),
          },
          {
            key: 'executions',
            label: '执行日志',
            children: (
              <QueryBoundary query={execsQ}>
                {() => (
                  <Table<JobExecutionResponse>
                    rowKey="id"
                    columns={execColumns}
                    dataSource={executions}
                    loading={execsQ.isFetching && !execsQ.data}
                    pagination={{ ...defaultPagination, defaultPageSize: 50 }}
                    size="middle"
                  />
                )}
              </QueryBoundary>
            ),
          },
        ]}
      />
    </div>
  );
}
