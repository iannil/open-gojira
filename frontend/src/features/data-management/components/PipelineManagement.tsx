import { useState } from 'react';
import {
  Button,
  Card,
  Input,
  InputNumber,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
} from 'antd';
import { PlayCircleOutlined, RedoOutlined, StopOutlined } from '@ant-design/icons';

import type { PipelineRunDetail as RunDetail } from '../../../api/types';
import {
  DATA_TYPE_LABELS,
  PIPELINE_STATUS_COLORS,
  PIPELINE_STATUS_LABELS,
  type DataTypeKey,
} from '../constants';
import PipelineProgressTracker from './PipelineProgressTracker';
import PipelineRunDetailDrawer from './PipelineRunDetail';
import {
  useActivePipelineRunQuery,
  usePipelineRunsQuery,
} from '../useDataQueries';
import {
  useCancelPipelineRunMutation,
  useRetryPipelineRunMutation,
  useStartPipelineRunMutation,
} from '../useDataMutations';

export default function PipelineManagement() {
  const [pipelineType, setPipelineType] = useState<DataTypeKey>('valuations');
  const [years, setYears] = useState(5);
  const [detailRun, setDetailRun] = useState<RunDetail | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);

  const runsQ = usePipelineRunsQuery(30);
  const activeRunQ = useActivePipelineRunQuery(activeRunId);

  const startM = useStartPipelineRunMutation();
  const retryM = useRetryPipelineRunMutation();
  const cancelM = useCancelPipelineRunMutation();

  const runs = runsQ.data ?? [];
  const activeRun = activeRunQ.data;
  const displayRuns = activeRun
    ? runs.map((r) => (r.run_id === activeRun.run_id ? activeRun : r))
    : runs;

  const handleStart = async () => {
    const res = await startM.mutateAsync({
      pipelineType,
      config: { years },
    });
    setActiveRunId(res.run_id);
  };

  const handleRetry = async (runId: string) => {
    const res = await retryM.mutateAsync(runId);
    setActiveRunId(res.run_id);
  };

  const handleCancel = async (runId: string) => {
    await cancelM.mutateAsync(runId);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
      <Card className="gojira-card" bordered={false} title="启动 Pipeline" size="small">
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
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={handleStart}
            loading={startM.isPending}
          >
            启动同步
          </Button>
        </Space>
        {activeRun && (activeRun.status === 'pending' || activeRun.status === 'running') && (
          <PipelineProgressTracker run={activeRun} />
        )}
      </Card>

      <Card className="gojira-card" bordered={false} title="运行历史" size="small">
        <Table
          dataSource={displayRuns}
          rowKey="run_id"
          loading={runsQ.isLoading}
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
                <Tag color={PIPELINE_STATUS_COLORS[v]}>
                  {PIPELINE_STATUS_LABELS[v] ?? v}
                </Tag>
              ),
            },
            {
              title: '进度',
              width: 160,
              render: (_: unknown, r: RunDetail) =>
                r.status === 'pending' || r.status === 'running' ? (
                  <PipelineProgressTracker run={r} />
                ) : (
                  <span className="num">
                    {r.completed_items}/{r.total_items}
                  </span>
                ),
            },
            {
              title: '失败',
              dataIndex: 'failed_items',
              width: 60,
              render: (v: number) =>
                v > 0 ? <Tag color="error">{v}</Tag> : <span className="num">0</span>,
            },
            {
              title: '创建时间',
              dataIndex: 'created_at',
              width: 170,
              render: (v: string) =>
                v ? (
                  <span
                    className="num"
                    style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}
                  >
                    {new Date(v).toLocaleString('zh-CN')}
                  </span>
                ) : (
                  '-'
                ),
            },
            {
              title: '操作',
              width: 180,
              render: (_: unknown, r: RunDetail) => (
                <Space size="small">
                  <Button size="small" onClick={() => setDetailRun(r)}>
                    详情
                  </Button>
                  {r.failed_items > 0 && r.status !== 'running' && (
                    <Popconfirm
                      title="重试失败项？"
                      onConfirm={() => handleRetry(r.run_id)}
                    >
                      <Button size="small" icon={<RedoOutlined />} loading={retryM.isPending}>
                        重试
                      </Button>
                    </Popconfirm>
                  )}
                  {(r.status === 'pending' || r.status === 'running') && (
                    <Popconfirm
                      title="取消此运行？"
                      onConfirm={() => handleCancel(r.run_id)}
                    >
                      <Button size="small" danger icon={<StopOutlined />} loading={cancelM.isPending}>
                        取消
                      </Button>
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
