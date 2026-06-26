/**
 * Phase 3 — Eval Set 页面
 *
 * 展示 LLM 质量基线 runs，支持创建新 run、查看详情、对比差异。
 */
import { useEffect, useState } from 'react';

import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DiffOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons';
import type { TableColumnsType } from 'antd';
import { useSearchParams } from 'react-router-dom';

import { apiClient } from '../../api/client';
import { PageHeader } from '../../components/primitives';

const { Text, Title } = Typography;

interface EvalRunSummary {
  id: number;
  label: string;
  status: string;
  pipeline_type: string;
  stock_count: number;
  passed: number;
  failed: number;
  total_cost_usd: number | null;
  created_at: string | null;
  finished_at: string | null;
}

interface EvalRunDetail extends EvalRunSummary {
  summary_json: Record<string, unknown> | null;
  error_message: string | null;
  items: EvalRunItem[];
}

interface EvalRunItem {
  id: number;
  stock_code: string;
  stock_name: string | null;
  status: string;
  score: number | null;
  score_label: string | null;
  duration_ms: number | null;
  cost_usd: number | null;
  conflict_count: number;
  red_line_triggered: boolean;
  output_summary: string | null;
  error_message: string | null;
}

interface EvalDiff {
  stock_code: string;
  stock_name: string;
  score_before: number | null;
  score_after: number | null;
  score_diff: number;
  duration_diff_ms: number;
  cost_diff_usd: number;
  status_changed: boolean;
  conflict_changed: boolean;
  red_line_changed: boolean;
  output_before: string | null;
  output_after: string | null;
}

interface CompareResult {
  run_1: { id: number; label: string; created_at: string | null };
  run_2: { id: number; label: string; created_at: string | null };
  changed_count: number;
  total_stocks: number;
  changes: EvalDiff[];
}

const PIPELINE_OPTIONS = [
  { value: 'quality_screen', label: 'Quality Screen' },
  { value: 'deep_research', label: 'Deep Research' },
];

export default function EvalSetPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [runs, setRuns] = useState<EvalRunSummary[]>([]);
  const [selectedRun, setSelectedRun] = useState<EvalRunDetail | null>(null);
  const [compareResult, setCompareResult] = useState<CompareResult | null>(null);
  const [compareRunId, setCompareRunId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // view state managed via searchParams
  searchParams.get('view'); // keep param reactive

  const fetchRuns = () => {
    setLoading(true);
    apiClient.get('/eval/runs')
      .then(res => setRuns(res.data))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchRuns(); }, []);

  const loadRun = (id: number) => {
    setLoading(true);
    setSelectedRun(null);
    setCompareResult(null);
    apiClient.get(`/eval/runs/${id}`)
      .then(res => setSelectedRun(res.data))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
    setSearchParams({ view: 'detail', run_id: String(id) }, { replace: true });
  };

  const createRun = async (pipelineType: string) => {
    setCreating(true);
    try {
      await apiClient.post(`/eval/runs?pipeline_type=${pipelineType}`);
      fetchRuns();
    } catch (e: unknown) {
      setError(String(e));
    } finally {
      setCreating(false);
    }
  };

  const doCompare = async () => {
    if (!selectedRun || !compareRunId) return;
    setLoading(true);
    try {
      const res = await apiClient.get('/eval/compare', {
        params: { run_id_1: selectedRun.id, run_id_2: compareRunId },
      });
      setCompareResult(res.data);
    } catch (e: unknown) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const backToList = () => {
    setSelectedRun(null);
    setCompareResult(null);
    setSearchParams({}, { replace: true });
  };

  if (loading) return <Spin tip="加载中…" style={{ display: 'block', marginTop: 48 }} />;

  const runColumns: TableColumnsType<EvalRunSummary> = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '标签', dataIndex: 'label', ellipsis: true },
    { title: 'Pipeline', dataIndex: 'pipeline_type', width: 140 },
    {
      title: '状态', dataIndex: 'status', width: 100,
      render: (s: string) => <Tag color={s === 'completed' ? 'green' : s === 'failed' ? 'red' : 'blue'}>{s}</Tag>,
    },
    { title: '股票数', dataIndex: 'stock_count', width: 80 },
    { title: '通过', dataIndex: 'passed', width: 60 },
    { title: '失败', dataIndex: 'failed', width: 60 },
    {
      title: '总成本', dataIndex: 'total_cost_usd', width: 100,
      render: (v: number | null) => v != null ? `$${v.toFixed(4)}` : '-',
    },
    {
      title: '操作', width: 120,
      render: (_: unknown, record: EvalRunSummary) => (
        <Button size="small" onClick={() => loadRun(record.id)}>查看</Button>
      ),
    },
  ];

  const itemColumns: TableColumnsType<EvalRunItem> = [
    { title: '代码', dataIndex: 'stock_code', width: 80 },
    { title: '名称', dataIndex: 'stock_name', width: 120 },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (s: string) => (
        <Tag icon={s === 'completed' ? <CheckCircleOutlined /> : s === 'failed' ? <CloseCircleOutlined /> : undefined}
          color={s === 'completed' ? 'success' : s === 'failed' ? 'error' : 'default'}>{s}</Tag>
      ),
    },
    { title: '评分', dataIndex: 'score', width: 80, render: (v: number | null) => v?.toFixed(2) ?? '-' },
    { title: '等级', dataIndex: 'score_label', width: 80 },
    { title: '耗时(ms)', dataIndex: 'duration_ms', width: 90 },
    { title: '成本', dataIndex: 'cost_usd', width: 80, render: (v: number | null) => v != null ? `$${v.toFixed(4)}` : '-' },
    { title: '冲突', dataIndex: 'conflict_count', width: 60 },
    {
      title: '红线', dataIndex: 'red_line_triggered', width: 60,
      render: (v: boolean) => v ? <Tag color="red">是</Tag> : '-',
    },
    { title: '输出摘要', dataIndex: 'output_summary', ellipsis: true },
    { title: '错误', dataIndex: 'error_message', ellipsis: true, render: (v: string | null) => v && <Text type="danger">{v}</Text> },
  ];

  const diffColumns: TableColumnsType<EvalDiff> = [
    { title: '代码', dataIndex: 'stock_code', width: 80 },
    { title: '名称', dataIndex: 'stock_name', width: 100 },
    {
      title: '分数变化', dataIndex: 'score_diff', width: 100,
      render: (v: number) => (
        <Tag color={v > 0.1 ? 'green' : v < -0.1 ? 'red' : 'default'}>{v > 0 ? '+' : ''}{v.toFixed(2)}</Tag>
      ),
    },
    {
      title: 'Before', dataIndex: 'score_before', width: 80,
      render: (v: number | null) => v?.toFixed(2) ?? '-',
    },
    {
      title: 'After', dataIndex: 'score_after', width: 80,
      render: (v: number | null) => v?.toFixed(2) ?? '-',
    },
    {
      title: '变更类型', key: 'changes', width: 200,
      render: (_: unknown, r: EvalDiff) => (
        <Space size={4}>
          {r.status_changed && <Tag color="orange">状态</Tag>}
          {r.conflict_changed && <Tag color="purple">冲突</Tag>}
          {r.red_line_changed && <Tag color="red">红线</Tag>}
          {!r.status_changed && !r.conflict_changed && !r.red_line_changed && <Tag>分数</Tag>}
        </Space>
      ),
    },
    { title: 'Before 摘要', dataIndex: 'output_before', ellipsis: true, width: 200 },
    { title: 'After 摘要', dataIndex: 'output_after', ellipsis: true, width: 200 },
  ];

  return (
    <div>
      <PageHeader
        title="Eval Set"
        enLabel="LLM Quality Baseline"
        purpose="在固定股票列表上运行 LLM Pipeline，跟踪评分/成本/冲突率变化，检测 Prompt Drift。"
      />

      {/* ── 列表视图 ──────────────────────────────────────────────────────── */}
      {!selectedRun && (
        <>
          {error && <Alert type="error" message={error} closable style={{ marginBottom: 16 }} />}

          <Space style={{ marginBottom: 16 }}>
            {PIPELINE_OPTIONS.map(opt => (
              <Button
                key={opt.value}
                icon={<PlayCircleOutlined />}
                loading={creating}
                onClick={() => createRun(opt.value)}
              >
                新建 {opt.label}
              </Button>
            ))}
          </Space>

          <Table
            dataSource={runs}
            columns={runColumns}
            rowKey="id"
            size="small"
            pagination={false}
          />
        </>
      )}

      {/* ── 详情视图 ──────────────────────────────────────────────────────── */}
      {selectedRun && (
        <>
          <Button onClick={backToList} style={{ marginBottom: 16 }}>← 返回列表</Button>

          <Card size="small" style={{ marginBottom: 16 }}>
            <Descriptions column={4} size="small">
              <Descriptions.Item label="标签">{selectedRun.label}</Descriptions.Item>
              <Descriptions.Item label="Pipeline">{selectedRun.pipeline_type}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={selectedRun.status === 'completed' ? 'green' : 'blue'}>{selectedRun.status}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="股票数">{selectedRun.stock_count}</Descriptions.Item>
              <Descriptions.Item label="通过">{selectedRun.passed}</Descriptions.Item>
              <Descriptions.Item label="失败">{selectedRun.failed}</Descriptions.Item>
              <Descriptions.Item label="总成本">
                {selectedRun.total_cost_usd != null ? `$${selectedRun.total_cost_usd.toFixed(4)}` : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">{selectedRun.created_at}</Descriptions.Item>
            </Descriptions>
          </Card>

          {/* ── 对比区 ──────────────────────────────────────────────────── */}
          <Card size="small" title="对比其他 Run" style={{ marginBottom: 16 }}>
            <Space>
              <Select
                placeholder="选择对比的 Run"
                style={{ width: 300 }}
                value={compareRunId}
                onChange={setCompareRunId}
                options={runs
                  .filter(r => r.id !== selectedRun.id)
                  .map(r => ({ value: r.id, label: `#${r.id} ${r.label}` }))
                }
              />
              <Button icon={<DiffOutlined />} onClick={doCompare} disabled={!compareRunId}>对比</Button>
            </Space>
            {compareResult && (
              <div style={{ marginTop: 16 }}>
                <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
                  <Col span={8}><Statistic title="对比 Run 1" value={compareResult.run_1.label} /></Col>
                  <Col span={8}><Statistic title="对比 Run 2" value={compareResult.run_2.label} /></Col>
                  <Col span={8}>
                    <Statistic
                      title="差异股票数"
                      value={compareResult.changed_count}
                      suffix={`/ ${compareResult.total_stocks}`}
                      valueStyle={{ color: compareResult.changed_count > 0 ? '#cf1322' : '#3f8600' }}
                    />
                  </Col>
                </Row>
                {compareResult.changes.length > 0 ? (
                  <Table
                    dataSource={compareResult.changes}
                    columns={diffColumns}
                    rowKey="stock_code"
                    size="small"
                    pagination={false}
                  />
                ) : (
                  <Text type="secondary">两个 Run 之间无差异</Text>
                )}
              </div>
            )}
          </Card>

          {/* ── 股票结果表 ────────────────────────────────────────────────── */}
          <Title level={5}>股票结果</Title>
          <Table
            dataSource={selectedRun.items}
            columns={itemColumns}
            rowKey="id"
            size="small"
            pagination={false}
          />
        </>
      )}
    </div>
  );
}
