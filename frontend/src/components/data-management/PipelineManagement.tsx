import { useCallback, useEffect, useState } from 'react';
import { Button, Card, Input, InputNumber, Popconfirm, Select, Space, Table, Tag } from 'antd';
import { PlayCircleOutlined, RedoOutlined, StopOutlined } from '@ant-design/icons';

import { listPipelineRuns, startPipelineRun, retryPipelineRun, cancelPipelineRun } from '../../api/client';
import type { PipelineRunDetail as RunDetail } from '../../api/types';
import { DATA_TYPE_LABELS, PIPELINE_STATUS_COLORS, PIPELINE_STATUS_LABELS, type DataTypeKey } from './constants';
import PipelineProgressTracker from './PipelineProgressTracker';
import PipelineRunDetailDrawer from './PipelineRunDetail';
import { usePipelinePolling } from './hooks/usePipelinePolling';
import { useAntdStatic } from '../../hooks/useAntdStatic';

interface Props {
  onPipelineComplete: () => void;
}

export default function PipelineManagement({ onPipelineComplete }: Props) {
  const { message } = useAntdStatic();
  const [runs, setRuns] = useState<RunDetail[]>([]);
  const [loading, setLoading] = useState(false);
  const [pipelineType, setPipelineType] = useState<DataTypeKey>('valuations');
  const [years, setYears] = useState(5);
  const [detailRun, setDetailRun] = useState<RunDetail | null>(null);

  const { activeRun, startPolling } = usePipelinePolling();

  const loadRuns = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listPipelineRuns({ limit: 30 });
      setRuns(data);
    } catch {
      message.error('加载运行历史失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadRuns(); }, [loadRuns]);

  // When active run finishes, refresh
  useEffect(() => {
    if (activeRun && activeRun.status !== 'pending' && activeRun.status !== 'running') {
      loadRuns();
      onPipelineComplete();
    }
  }, [activeRun, loadRuns, onPipelineComplete]);

  const handleStart = async () => {
    try {
      const res = await startPipelineRun(pipelineType, { years });
      message.success(`已启动 ${DATA_TYPE_LABELS[pipelineType]} Pipeline (Run: ${res.run_id})`);
      startPolling(res.run_id);
      await loadRuns();
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || '启动 Pipeline 失败');
    }
  };

  const handleRetry = async (runId: string) => {
    try {
      const res = await retryPipelineRun(runId);
      message.success(`已重试 (New Run: ${res.run_id})`);
      startPolling(res.run_id);
      await loadRuns();
    } catch {
      message.error('重试失败');
    }
  };

  const handleCancel = async (runId: string) => {
    try {
      await cancelPipelineRun(runId);
      message.info('已请求取消');
      await loadRuns();
    } catch {
      message.error('取消失败');
    }
  };

  // Merge active run into runs list for real-time progress
  const displayRuns = activeRun
    ? runs.map((r) => r.run_id === activeRun.run_id ? activeRun : r)
    : runs;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card title="启动 Pipeline" size="small">
        <Space wrap>
          <Select
            value={pipelineType}
            onChange={(v) => setPipelineType(v)}
            style={{ width: 140 }}
            options={Object.entries(DATA_TYPE_LABELS).map(([k, v]) => ({ value: k, label: v }))}
          />
          <Space.Compact>
            <Input style={{ width: 48, textAlign: 'center' }} value="年数" disabled />
            <InputNumber value={years} onChange={(v) => setYears(v ?? 5)} min={1} max={20} />
          </Space.Compact>
          <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleStart}>
            启动同步
          </Button>
        </Space>
        {activeRun && (activeRun.status === 'pending' || activeRun.status === 'running') && (
          <PipelineProgressTracker run={activeRun} />
        )}
      </Card>

      <Card title="运行历史" size="small">
        <Table
          dataSource={displayRuns}
          rowKey="run_id"
          loading={loading}
          size="small"
          pagination={{ pageSize: 10 }}
          scroll={{ x: 900 }}
          columns={[
            {
              title: '类型',
              dataIndex: 'pipeline_type',
              width: 100,
              render: (v: string) => DATA_TYPE_LABELS[v as DataTypeKey] ?? v,
            },
            {
              title: '状态',
              dataIndex: 'status',
              width: 100,
              render: (v: string) => (
                <Tag color={PIPELINE_STATUS_COLORS[v]}>{PIPELINE_STATUS_LABELS[v] ?? v}</Tag>
              ),
            },
            {
              title: '进度',
              width: 160,
              render: (_: unknown, r: RunDetail) =>
                r.status === 'pending' || r.status === 'running'
                  ? <PipelineProgressTracker run={r} />
                  : `${r.completed_items}/${r.total_items}`,
            },
            {
              title: '失败',
              dataIndex: 'failed_items',
              width: 60,
              render: (v: number) => v > 0 ? <Tag color="error">{v}</Tag> : 0,
            },
            {
              title: '创建时间',
              dataIndex: 'created_at',
              width: 170,
              render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-',
            },
            {
              title: '操作',
              width: 180,
              render: (_: unknown, r: RunDetail) => (
                <Space size="small">
                  <Button size="small" onClick={() => setDetailRun(r)}>详情</Button>
                  {r.failed_items > 0 && r.status !== 'running' && (
                    <Popconfirm title="重试失败项？" onConfirm={() => handleRetry(r.run_id)}>
                      <Button size="small" icon={<RedoOutlined />}>重试</Button>
                    </Popconfirm>
                  )}
                  {(r.status === 'pending' || r.status === 'running') && (
                    <Popconfirm title="取消此运行？" onConfirm={() => handleCancel(r.run_id)}>
                      <Button size="small" danger icon={<StopOutlined />}>取消</Button>
                    </Popconfirm>
                  )}
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <PipelineRunDetailDrawer
        run={detailRun}
        open={!!detailRun}
        onClose={() => setDetailRun(null)}
      />
    </div>
  );
}
