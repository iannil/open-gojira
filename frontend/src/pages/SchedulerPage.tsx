import { useCallback, useEffect, useState } from 'react';
import {
  Button,
  Input,
  Popconfirm,
  Switch,
  Table,
  Tabs,
  Tag,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  PlayCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';

import {
  listJobExecutions,
  listSchedulerJobs,
  triggerSchedulerJob,
  updateSchedulerJob,
} from '../api/client';
import { useAntdStatic } from '../hooks/useAntdStatic';
import PageHeader from '../components/PageHeader';
import type {
  JobExecutionResponse,
  SchedulerJobResponse,
} from '../api/types';

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
    '0': '周日', '1': '周一', '2': '周二', '3': '周三',
    '4': '周四', '5': '周五', '6': '周六', '7': '周日',
    '1-5': '工作日',
  };

  const monMap: Record<string, string> = {
    '1': '1月', '2': '2月', '3': '3月', '4': '4月',
    '5': '5月', '6': '6月', '7': '7月', '8': '8月',
    '9': '9月', '10': '10月', '11': '11月', '12': '12月',
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
  const { message } = useAntdStatic();
  const [jobs, setJobs] = useState<SchedulerJobResponse[]>([]);
  const [executions, setExecutions] = useState<JobExecutionResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [execLoading, setExecLoading] = useState(false);
  const [editingJob, setEditingJob] = useState<string | null>(null);
  const [editCron, setEditCron] = useState('');
  const [triggering, setTriggering] = useState<string | null>(null);

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listSchedulerJobs();
      setJobs(data);
    } catch {
      message.error('获取任务列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchExecutions = useCallback(async () => {
    setExecLoading(true);
    try {
      const data = await listJobExecutions(undefined, 100);
      setExecutions(data);
    } catch {
      message.error('获取执行日志失败');
    } finally {
      setExecLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchJobs();
    fetchExecutions();
  }, [fetchJobs, fetchExecutions]);

  const handleToggle = async (jobId: string, enabled: boolean) => {
    try {
      await updateSchedulerJob(jobId, { enabled });
      message.success(enabled ? '已启用' : '已停用');
      fetchJobs();
    } catch {
      message.error('更新失败');
    }
  };

  const handleCronSave = async (jobId: string) => {
    try {
      await updateSchedulerJob(jobId, { cron_expr: editCron });
      message.success('Cron 已更新');
      setEditingJob(null);
      fetchJobs();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Cron 格式无效';
      message.error(msg);
    }
  };

  const handleTrigger = async (jobId: string) => {
    setTriggering(jobId);
    try {
      await triggerSchedulerJob(jobId);
      message.success('执行完成');
      fetchJobs();
      fetchExecutions();
    } catch {
      message.error('执行失败');
    } finally {
      setTriggering(null);
    }
  };

  const jobColumns: ColumnsType<SchedulerJobResponse> = [
    {
      title: '任务 ID',
      dataIndex: 'job_id',
      width: 200,
      render: (v: string) => <code style={{ fontSize: 13 }}>{v}</code>,
    },
    {
      title: '描述',
      dataIndex: 'description',
      ellipsis: true,
    },
    {
      title: '调度规则',
      dataIndex: 'cron_expr',
      width: 240,
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
              style={{ width: 220 }}
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
            style={{ cursor: 'pointer', borderBottom: '1px dashed var(--gray-300)' }}
            title="点击编辑"
          >
            <code>{cron}</code>
            <span style={{ color: 'var(--gray-400)', fontSize: 12, marginLeft: 8 }}>
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
          onChange={(v) => handleToggle(record.job_id, v)}
        />
      ),
    },
    {
      title: '上次执行',
      width: 180,
      render: (_: unknown, record: SchedulerJobResponse) => (
        <span>
          {record.last_run_status === 'success' && (
            <CheckCircleOutlined style={{ color: 'var(--green-600)', marginRight: 4 }} />
          )}
          {record.last_run_status === 'failed' && (
            <ExclamationCircleOutlined style={{ color: 'var(--red-600)', marginRight: 4 }} />
          )}
          {formatTime(record.last_run_at)}
          {record.last_duration_ms != null && (
            <span style={{ color: 'var(--gray-400)', fontSize: 12, marginLeft: 4 }}>
              ({formatDuration(record.last_duration_ms)})
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
        record.enabled ? formatTime(v) : <span style={{ color: 'var(--gray-400)' }}>-</span>,
    },
    {
      title: '操作',
      width: 100,
      render: (_: unknown, record: SchedulerJobResponse) => (
        <Popconfirm
          title={`确认手动执行 ${record.job_id}?`}
          onConfirm={() => handleTrigger(record.job_id)}
        >
          <Button
            type="link"
            size="small"
            icon={<PlayCircleOutlined />}
            loading={triggering === record.job_id}
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
      render: (v: string) => <code style={{ fontSize: 13 }}>{v}</code>,
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
          color={s === 'success' ? 'success' : s === 'failed' ? 'error' : 'processing'}
        >
          {s === 'success' ? '成功' : s === 'failed' ? '失败' : '运行中'}
        </Tag>
      ),
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      width: 170,
      render: (v: string | null) => formatTime(v),
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      width: 80,
      render: (v: number | null) => formatDuration(v),
    },
    {
      title: '结果',
      dataIndex: 'result_summary',
      ellipsis: true,
      render: (v: string | null) =>
        v ? (
          <span style={{ color: 'var(--gray-600)', fontSize: 12 }}>{v.slice(0, 120)}</span>
        ) : (
          '-'
        ),
    },
    {
      title: '错误',
      dataIndex: 'error_message',
      ellipsis: true,
      render: (v: string | null) =>
        v ? <span style={{ color: 'var(--red-600)', fontSize: 12 }}>{v}</span> : '-',
    },
  ];

  const enabledCount = jobs.filter((j) => j.enabled).length;

  return (
    <div>
      <PageHeader
        title="定时任务"
        enLabel="Scheduler"
        icon={<ClockCircleOutlined />}
        description={`共 ${jobs.length} 个任务，${enabledCount} 个启用`}
      />

      <Tabs
        defaultActiveKey="jobs"
        items={[
          {
            key: 'jobs',
            label: '任务管理',
            children: (
              <Table<SchedulerJobResponse>
                rowKey="job_id"
                columns={jobColumns}
                dataSource={jobs}
                loading={loading}
                pagination={false}
                size="middle"
              />
            ),
          },
          {
            key: 'executions',
            label: '执行日志',
            children: (
              <Table<JobExecutionResponse>
                rowKey="id"
                columns={execColumns}
                dataSource={executions}
                loading={execLoading}
                pagination={{ pageSize: 20, showSizeChanger: false }}
                size="middle"
              />
            ),
          },
        ]}
      />
    </div>
  );
}
