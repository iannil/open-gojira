import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Button,
  Col,
  Row,
  Spin,
  Tabs,
  Tag,
  Table,
  Card,
  Space,
  Modal,
  Select,
  InputNumber,
  Tooltip,
  Typography,
  message,
  Alert,
} from 'antd';
import {
  ArrowLeftOutlined,
  PlayCircleOutlined,
  ExportOutlined,
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  exportResearchRun,
  getResearchTheme,
  getResearchRun,
  listResearchRuns,
  triggerResearchRun,
} from '../../api/client';
import { RunDiffDrawer } from './RunDiffDrawer';
import type {
  ResearchCompanyRankingRow,
  ResearchCompanyUniverseRow,
  ResearchEvidenceRow,
  ResearchRunSummary,
  ScarceLayer,
  ValueChainLayer,
} from '../../api/types';

const GRADE_COLOR: Record<string, string> = {
  strong: 'green',
  medium: 'blue',
  weak: 'orange',
  lead: 'default',
};

const CLASSIFICATION_LABEL: Record<string, string> = {
  controls: '控制稀缺层',
  supplies: '供应稀缺层',
  benefits: '受益',
  weak: '弱定价权',
  story: '故事为主',
};

export default function ResearchThemeDetailPage() {
  const params = useParams();
  const themeId = Number(params.themeId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const themeQ = useQuery({
    queryKey: ['research-theme', themeId],
    queryFn: () => getResearchTheme(themeId),
    enabled: !!themeId,
  });

  const runsQ = useQuery({
    queryKey: ['research-runs', themeId],
    queryFn: () => listResearchRuns(themeId),
    enabled: !!themeId,
  });

  const triggerM = useMutation({
    mutationFn: () => triggerResearchRun(themeId),
    onSuccess: (run) => {
      message.success(`已触发 Run #${run.id},后台执行中(预计 3-5 分钟)`);
      queryClient.invalidateQueries({ queryKey: ['research-runs', themeId] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : '触发失败';
      message.error(msg);
    },
  });

  if (!themeQ.data) {
    return <Spin spinning style={{ padding: 40 }} />;
  }

  const theme = themeQ.data;
  const latestRun = runsQ.data?.[0];

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Button
          icon={<ArrowLeftOutlined />}
          type="link"
          onClick={() => navigate('/research')}
          style={{ padding: 0 }}
        >
          返回研究方向列表
        </Button>
      </div>

      <Card
        title={
          <Space>
            <strong>{theme.name}</strong>
            <Tag>{theme.market}</Tag>
            <Tag color="purple">{theme.auto_refresh_freq}</Tag>
            {theme.last_run_status && (
              <Tag color={
                theme.last_run_status === 'completed' ? 'green' :
                theme.last_run_status === 'failed' ? 'red' : 'blue'
              }>
                last: {theme.last_run_status}
              </Tag>
            )}
          </Space>
        }
        extra={
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={triggerM.isPending}
            onClick={() => triggerM.mutate()}
            disabled={theme.status !== 'active'}
          >
            运行 Serenity 研究
          </Button>
        }
      >
        {theme.description && (
          <div style={{ marginBottom: 12, color: '#57534E' }}>
            {theme.description}
          </div>
        )}
        {theme.last_run_error && (
          <Alert
            type="error"
            message="最近一次运行失败"
            description={theme.last_run_error}
            style={{ marginBottom: 12 }}
          />
        )}
        <div style={{ fontSize: 12, color: '#78716C' }}>
          最近运行: {theme.last_run_at
            ? new Date(theme.last_run_at).toLocaleString('zh-CN')
            : '从未运行'}
        </div>
      </Card>

      <div style={{ marginTop: 16 }}>
        <Tabs
          items={[
            {
              key: 'overview',
              label: '概览',
              children: latestRun ? (
                <RunOverview run={latestRun} themeId={themeId} />
              ) : (
                <Alert
                  type="info"
                  message="还没有 Run 记录"
                  description="点击右上角「运行 Serenity 研究」触发首次研究。"
                />
              ),
            },
            {
              key: 'value-chain',
              label: '价值链 8 层',
              children: latestRun ? (
                <RunValueChainTab latestRunId={latestRun.id} />
              ) : <EmptyRunNotice />,
            },
            {
              key: 'companies',
              label: '公司宇宙',
              children: latestRun ? (
                <RunCompaniesTab latestRunId={latestRun.id} />
              ) : <EmptyRunNotice />,
            },
            {
              key: 'evidence',
              label: '证据链',
              children: latestRun ? (
                <RunEvidenceTab latestRunId={latestRun.id} />
              ) : <EmptyRunNotice />,
            },
            {
              key: 'failure',
              label: '失败条件 & 下一步',
              children: latestRun ? (
                <RunFailureTab latestRunId={latestRun.id} />
              ) : <EmptyRunNotice />,
            },
            {
              key: 'history',
              label: '历史 Run',
              children: <RunHistoryTab runs={runsQ.data ?? []} />,
            },
          ]}
        />
      </div>
    </div>
  );
}


// ── Tabs ────────────────────────────────────────────────────────────────

function EmptyRunNotice() {
  return (
    <Alert
      type="info"
      message="还没有完成的 Run"
      description="首次研究触发后,这里会显示完整结果。"
    />
  );
}

function RunOverview({ run, themeId }: { run: ResearchRunSummary; themeId: number }) {
  const runDetailQ = useQuery({
    queryKey: ['research-run', run.id],
    queryFn: () => getResearchRun(run.id),
    enabled: run.status === 'completed',
  });
  const [exportOpen, setExportOpen] = useState(false);

  if (run.status === 'running') {
    return (
      <Alert
        type="info"
        message={`Run #${run.id} 正在执行中…`}
        description={`触发时间: ${new Date(run.started_at).toLocaleString('zh-CN')}`}
      />
    );
  }
  if (run.status === 'failed') {
    return (
      <Alert
        type="error"
        message={`Run #${run.id} 失败`}
        description={`点击「历史 Run」tab 查看详情,或重新触发研究。`}
      />
    );
  }
  if (!runDetailQ.data) {
    return <Spin spinning />;
  }

  const detail = runDetailQ.data;
  const scarce = detail.scarce_layers ?? [];
  const ranking = detail.company_ranking ?? [];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small">
            <div style={{ fontSize: 12, color: '#78716C' }}>Token Input</div>
            <div style={{ fontSize: 18 }}>{run.llm_token_input.toLocaleString()}</div>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <div style={{ fontSize: 12, color: '#78716C' }}>Token Output</div>
            <div style={{ fontSize: 18 }}>{run.llm_token_output.toLocaleString()}</div>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <div style={{ fontSize: 12, color: '#78716C' }}>Web Search 次数</div>
            <div style={{ fontSize: 18 }}>{run.llm_search_count}</div>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <div style={{ fontSize: 12, color: '#78716C' }}>公司/证据/排名</div>
            <div style={{ fontSize: 18 }}>
              {detail.company_universe?.length ?? 0} / {detail.evidence?.length ?? 0} / {ranking.length}
            </div>
          </Card>
        </Col>
      </Row>

      <Card title="系统变化" size="small" style={{ marginBottom: 16 }}>
        {detail.system_change_md ? (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{detail.system_change_md}</ReactMarkdown>
        ) : (
          <em style={{ color: '#A8A29E' }}>无</em>
        )}
      </Card>

      <Card title="稀缺层排名" size="small" style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          {scarce.length === 0 ? (
            <em style={{ color: '#A8A29E' }}>无</em>
          ) : (
            scarce.sort((a, b) => a.rank - b.rank).map((s: ScarceLayer) => (
              <div
                key={s.id}
                style={{
                  border: '1px solid #E7E5E4',
                  borderRadius: 4,
                  padding: 12,
                }}
              >
                <Space>
                  <Tag color="red">#{s.rank}</Tag>
                  {s.layer_name && <strong>{s.layer_name}</strong>}
                  <Tag color={
                    s.expansion_difficulty === 'high' ? 'red' :
                    s.expansion_difficulty === 'medium' ? 'orange' : 'default'
                  }>
                    扩产: {s.expansion_difficulty}
                  </Tag>
                </Space>
                <div style={{ marginTop: 8, color: '#57534E' }}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{s.scarcity_reason_md}</ReactMarkdown>
                </div>
              </div>
            ))
          )}
        </Space>
      </Card>

      <Card
        title={`Top ${ranking.length} 公司排名`}
        size="small"
        extra={
          <Button
            icon={<ExportOutlined />}
            size="small"
            onClick={() => setExportOpen(true)}
          >
            导出到自选股
          </Button>
        }
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          {ranking.length === 0 ? (
            <em style={{ color: '#A8A29E' }}>无</em>
          ) : (
            ranking.sort((a, b) => a.rank - b.rank).map((r: ResearchCompanyRankingRow) => (
              <div
                key={r.id}
                style={{
                  border: '1px solid #E7E5E4',
                  borderRadius: 4,
                  padding: 12,
                }}
              >
                <Space>
                  <Tag color="gold">#{r.rank}</Tag>
                  <strong>
                    <a href={`/stock/${r.stock_code}`}>{r.stock_code}</a>
                  </strong>
                  <span style={{ color: '#57534E' }}>{r.constrains_what}</span>
                  <Tag>{r.chain_position}</Tag>
                </Space>
                <div style={{ marginTop: 8, color: '#57534E' }}>
                  <strong>排序原因:</strong> {r.rank_reason_md}
                </div>
                <div style={{ marginTop: 4, color: '#57534E' }}>
                  <strong>证据摘要:</strong> {r.evidence_summary_md}
                </div>
                <div style={{ marginTop: 4, color: '#B91C1C' }}>
                  <strong>主要风险:</strong> {r.main_risk_md}
                </div>
              </div>
            ))
          )}
        </Space>
      </Card>

      <ExportModal
        open={exportOpen}
        runId={run.id}
        themeId={themeId}
        onClose={() => setExportOpen(false)}
      />
    </div>
  );
}

function RunValueChainTab({ latestRunId }: { latestRunId: number }) {
  const runQ = useQuery({
    queryKey: ['research-run', latestRunId],
    queryFn: () => getResearchRun(latestRunId),
  });
  if (!runQ.data) return <Spin spinning />;
  const layers = (runQ.data.value_chain_layers ?? []) as ValueChainLayer[];
  return (
    <Table
      rowKey="id"
      dataSource={layers}
      pagination={false}
      size="small"
      columns={[
        { title: '#', dataIndex: 'layer_index', width: 60 },
        { title: '层级', dataIndex: 'name' },
        { title: '描述', dataIndex: 'description' },
      ]}
    />
  );
}

function RunCompaniesTab({ latestRunId }: { latestRunId: number }) {
  const runQ = useQuery({
    queryKey: ['research-run', latestRunId],
    queryFn: () => getResearchRun(latestRunId),
  });
  if (!runQ.data) return <Spin spinning />;
  const rows = (runQ.data.company_universe ?? []) as ResearchCompanyUniverseRow[];
  return (
    <Table
      rowKey="id"
      dataSource={rows}
      pagination={{ pageSize: 50 }}
      size="small"
      columns={[
        {
          title: 'Code',
          dataIndex: 'stock_code',
          width: 100,
          render: (code: string) => <a href={`/stock/${code}`}>{code}</a>,
        },
        { title: '分类', dataIndex: 'classification', width: 120,
          render: (c: string) => (
            <Tag color={
              c === 'controls' ? 'red' :
              c === 'supplies' ? 'orange' :
              c === 'benefits' ? 'blue' :
              c === 'weak' ? 'default' : 'default'
            }>
              {CLASSIFICATION_LABEL[c] ?? c}
            </Tag>
          ),
        },
        { title: '层级', dataIndex: 'layer_name', width: 150 },
        { title: '备注', dataIndex: 'note' },
      ]}
    />
  );
}

function RunEvidenceTab({ latestRunId }: { latestRunId: number }) {
  const runQ = useQuery({
    queryKey: ['research-run', latestRunId],
    queryFn: () => getResearchRun(latestRunId),
  });
  if (!runQ.data) return <Spin spinning />;
  const rows = (runQ.data.evidence ?? []) as ResearchEvidenceRow[];
  return (
    <Table
      rowKey="id"
      dataSource={rows}
      pagination={{ pageSize: 50 }}
      size="small"
      columns={[
        { title: 'Grade', dataIndex: 'grade', width: 80,
          render: (g: string) => <Tag color={GRADE_COLOR[g] ?? 'default'}>{g}</Tag>,
        },
        { title: 'Type', dataIndex: 'source_type', width: 120 },
        { title: 'Code', dataIndex: 'stock_code', width: 100 },
        { title: '标题', dataIndex: 'source_title',
          render: (t: string, row: ResearchEvidenceRow) => (
            <a href={row.source_url} target="_blank" rel="noopener noreferrer">{t}</a>
          ),
        },
        { title: '日期', dataIndex: 'published_at', width: 110 },
        { title: '摘要', dataIndex: 'summary_md' },
      ]}
    />
  );
}

function RunFailureTab({ latestRunId }: { latestRunId: number }) {
  const runQ = useQuery({
    queryKey: ['research-run', latestRunId],
    queryFn: () => getResearchRun(latestRunId),
  });
  if (!runQ.data) return <Spin spinning />;
  return (
    <Row gutter={16}>
      <Col span={12}>
        <Card title="失败条件 (什么情况说明判断错了)" size="small">
          {runQ.data.failure_conditions_md ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {runQ.data.failure_conditions_md}
            </ReactMarkdown>
          ) : (
            <em style={{ color: '#A8A29E' }}>无</em>
          )}
        </Card>
      </Col>
      <Col span={12}>
        <Card title="下一步验证" size="small">
          {runQ.data.next_steps_md ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {runQ.data.next_steps_md}
            </ReactMarkdown>
          ) : (
            <em style={{ color: '#A8A29E' }}>无</em>
          )}
        </Card>
      </Col>
    </Row>
  );
}

function RunHistoryTab({ runs }: { runs: ResearchRunSummary[] }) {
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [diffOpen, setDiffOpen] = useState(false);

  if (runs.length === 0) {
    return <EmptyRunNotice />;
  }

  const completedCount = runs.filter(r => r.status === 'completed').length;
  const selectedRuns = runs.filter(r => selectedIds.includes(r.id));
  const canCompare = selectedIds.length === 2
    && selectedRuns.every(r => r.status === 'completed');

  const tooltip = selectedIds.length === 0
    ? '选择 2 个 Run'
    : selectedIds.length === 1
    ? '再选 1 个 Run'
    : selectedIds.length === 2
    ? selectedRuns.every(r => r.status === 'completed')
      ? '点击对比'
      : '两个 Run 都必须 completed'
    : '只能选 2 个 Run';

  const rowSelection = {
    selectedRowKeys: selectedIds,
    onChange: (keys: React.Key[]) => {
      // Allow max 2 selections; if user picks a 3rd, replace oldest
      const next = keys as number[];
      if (next.length > 2) {
        setSelectedIds(next.slice(-2));
      } else {
        setSelectedIds(next);
      }
    },
    getCheckboxProps: () => ({
      // Disable selection entirely if <2 completed runs available
      disabled: completedCount < 2,
    }),
  };

  return (
    <>
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography.Text type="secondary">
          勾选 2 个 completed Run 对比差异 (Phase 2 #10)
        </Typography.Text>
        <Tooltip title={canCompare ? '' : tooltip}>
          <Button
            type="primary"
            disabled={!canCompare}
            onClick={() => setDiffOpen(true)}
          >
            对比选中 ({selectedIds.length}/2)
          </Button>
        </Tooltip>
      </div>
      <Table
        rowKey="id"
        dataSource={runs}
        pagination={false}
        size="small"
        rowSelection={rowSelection}
        columns={[
          { title: 'Run', dataIndex: 'id', width: 80 },
          {
            title: '状态', dataIndex: 'status', width: 120,
            render: (s: string) => (
              <Tag color={
                s === 'completed' ? 'green' :
                s === 'failed' ? 'red' : 'blue'
              }>{s}</Tag>
            ),
          },
          { title: '触发', dataIndex: 'triggered_by', width: 100 },
          { title: 'Input Tokens', dataIndex: 'llm_token_input', width: 130,
            render: (v: number) => v.toLocaleString() },
          { title: 'Output Tokens', dataIndex: 'llm_token_output', width: 130,
            render: (v: number) => v.toLocaleString() },
          { title: 'Search', dataIndex: 'llm_search_count', width: 80 },
          { title: 'Started', dataIndex: 'started_at',
            render: (s: string) => new Date(s).toLocaleString('zh-CN') },
          { title: 'Completed', dataIndex: 'completed_at',
            render: (s: string | null) => s ? new Date(s).toLocaleString('zh-CN') : '—' },
        ]}
      />
      {diffOpen && selectedIds.length === 2 && (
        <RunDiffDrawer
          runAId={selectedIds[0]}
          runBId={selectedIds[1]}
          onClose={() => setDiffOpen(false)}
        />
      )}
    </>
  );
}


// ── Export Modal ────────────────────────────────────────────────────────

function ExportModal({
  open,
  runId,
  themeId,
  onClose,
}: {
  open: boolean;
  runId: number;
  themeId: number;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [rankMax, setRankMax] = useState(3);
  const [groupId, setGroupId] = useState<number | null>(null);

  // Load watchlist groups for Select
  const groupsQ = useQuery({
    queryKey: ['watchlist-groups'],
    queryFn: async () => {
      const { apiClient } = await import('../../api/client');
      const res = await apiClient.get('/watchlist/groups');
      return res.data;
    },
    enabled: open,
  });

  const exportM = useMutation({
    mutationFn: () => exportResearchRun(runId, {
      target: 'watchlist',
      rank_max: rankMax,
      watchlist_group_id: groupId!,
    }),
    onSuccess: (data) => {
      message.success(`已导出 ${data.exported_count} 家到自选股 (group=${data.target_id})`);
      queryClient.invalidateQueries({ queryKey: ['research-theme', themeId] });
      onClose();
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : '导出失败';
      message.error(msg);
    },
  });

  return (
    <Modal
      title="导出 Top N 到自选股"
      open={open}
      onCancel={onClose}
      onOk={() => exportM.mutate()}
      confirmLoading={exportM.isPending}
      okText="导出"
      cancelText="取消"
    >
      <div style={{ marginBottom: 12 }}>
        目标自选股分组:
        <Select
          style={{ width: '100%', marginTop: 4 }}
          placeholder="选择分组"
          value={groupId ?? undefined}
          onChange={(v) => setGroupId(v)}
          options={(groupsQ.data ?? []).map((g: { id: number; name: string }) => ({
            value: g.id,
            label: g.name,
          }))}
        />
      </div>
      <div>
        导出 Top N (1-7):
        <InputNumber
          min={1}
          max={7}
          value={rankMax}
          onChange={(v) => setRankMax(v ?? 3)}
          style={{ width: '100%', marginTop: 4 }}
        />
      </div>
      <Alert
        type="info"
        showIcon
        style={{ marginTop: 12 }}
        message="Q11: 导出不弹 DisciplineChecklistModal"
        description="候选股从自选股流入 Draft 时再过 Checklist。"
      />
    </Modal>
  );
}
