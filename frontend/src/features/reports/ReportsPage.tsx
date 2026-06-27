import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Empty,
  Input,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import { RedoOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import {
  listRecentReports,
  getReportById,
  triggerResearch,
  type PipelineType,
  type Recommendation,
  type ReportStatus,
  type ResearchReportFull,
  type ResearchReportSummary,
} from '../../api/research';
import PageHeader from '../../components/primitives/PageHeader';
import PageSection from '../../components/primitives/PageSection';

const { Text } = Typography;

const REC_COLORS: Record<Recommendation, string> = {
  BUY: 'success',
  HOLD: 'warning',
  PASS: 'default',
  SELL: 'error',
  TRIM: 'warning',
};

const STATUS_COLORS: Record<ReportStatus, string> = {
  running: 'processing',
  completed: 'success',
  rejected: 'error',
  conflict: 'warning',
  stale: 'default',
  failed: 'error',
};

const PIPELINE_OPTIONS: { label: string; value: PipelineType }[] = [
  { label: '全部 Pipeline', value: undefined as unknown as PipelineType },
  { label: '深度研究', value: 'deep_research' },
  { label: '论文追踪', value: 'thesis_tracker' },
  { label: '异动归因', value: 'news_pulse' },
  { label: '财报精读', value: 'earnings_review' },
  { label: '质量筛选', value: 'quality_screen' },
];

const PIPELINE_LABELS: Record<PipelineType, string> = {
  deep_research: '深度研究',
  thesis_tracker: '论文追踪',
  news_pulse: '异动归因',
  earnings_review: '财报精读',
  quality_screen: '质量筛选',
};

export default function ReportsPage() {
  const [pipelineFilter, setPipelineFilter] = useState<PipelineType | undefined>(undefined);
  const [selectedReportId, setSelectedReportId] = useState<number | null>(null);
  const [searchCode, setSearchCode] = useState('');

  const reportsQuery = useQuery({
    queryKey: ['research', 'reports', pipelineFilter],
    queryFn: () => listRecentReports(pipelineFilter, 100),
    refetchInterval: 60_000,
  });

  // Fetch full report details when a report is selected
  const reportDetailQuery = useQuery({
    queryKey: ['research', 'report', selectedReportId],
    queryFn: () => getReportById(selectedReportId!),
    enabled: selectedReportId !== null,
  });

  const reports = reportsQuery.data ?? [];
  const filtered = useMemo(() => {
    if (!searchCode.trim()) return reports;
    const q = searchCode.toLowerCase();
    return reports.filter((r) => r.stock_code.toLowerCase().includes(q));
  }, [reports, searchCode]);

  // When the list updates, re-select the same report if still present
  const selectedReport = useMemo(() => {
    const full = reportDetailQuery.data;
    if (full) return full;
    // If detail not yet loaded, fall back to summary data from the list
    if (selectedReportId !== null) {
      return reports.find((r) => r.id === selectedReportId) as unknown as ResearchReportFull ?? null;
    }
    return null;
  }, [reportDetailQuery.data, selectedReportId, reports]);

  // Retry mutation for failed/rejected reports
  const retryMutation = useMutation({
    mutationFn: (stockCode: string) => triggerResearch(stockCode, { force: true }),
    onSuccess: () => {
      // Refetch the reports list after triggering retry
      setTimeout(() => {
        reportsQuery.refetch();
      }, 2000);
    },
  });

  const handleRetry = (stockCode: string) => {
    retryMutation.mutate(stockCode);
  };

  return (
    <div>
      <PageHeader
        title="研究报告"
        enLabel="Reports"
        purpose="所有 v2 Pipeline 产出的研究报告（ai-berkshire 风格）"
        actions={
          <Button
            icon={<ReloadOutlined />}
            onClick={() => reportsQuery.refetch()}
            loading={reportsQuery.isFetching}
          >
            刷新
          </Button>
        }
      />

      <Row gutter={16}>
        {/* Left: Reports List */}
        <Col span={10}>
          <PageSection title={`报告列表 (${filtered.length})`}>
            <Space direction="vertical" style={{ width: '100%', marginBottom: 12 }}>
              <Input
                placeholder="按股票代码搜索..."
                prefix={<SearchOutlined />}
                value={searchCode}
                onChange={(e) => setSearchCode(e.target.value)}
                allowClear
              />
              <Select<PipelineType | undefined>
                style={{ width: '100%' }}
                value={pipelineFilter}
                onChange={(v) => setPipelineFilter(v)}
                options={PIPELINE_OPTIONS}
              />
            </Space>

            {filtered.length === 0 ? (
              <Empty
                description={
                  <Space direction="vertical">
                    <Text type="secondary">暂无报告</Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      去 <Link to="/universe">股票池</Link> 触发深度研究。
                    </Text>
                  </Space>
                }
              />
            ) : (
              <Table
                size="small"
                dataSource={filtered}
                rowKey="id"
                pagination={{ pageSize: 20 }}
                onRow={(r) => ({
                  onClick: () => setSelectedReportId(r.id),
                  style: { cursor: 'pointer' },
                })}
                rowClassName={(r) =>
                  r.id === selectedReportId ? 'ant-table-row-selected' : ''
                }
                columns={[
                  {
                    title: '股票',
                    dataIndex: 'stock_code',
                    render: (code: string, r: ResearchReportSummary) => (
                      <span>
                        <strong>{code}</strong>
                        {r.stock_name && (
                          <span style={{ color: 'var(--gray-500)', marginLeft: 6, fontSize: 'var(--fs-sm)' }}>
                            {r.stock_name}
                          </span>
                        )}
                      </span>
                    ),
                  },
                  {
                    title: 'Pipeline',
                    dataIndex: 'pipeline_type',
                    render: (pt: PipelineType) => (
                      <Tag>{PIPELINE_LABELS[pt] ?? pt}</Tag>
                    ),
                  },
                  {
                    title: '状态',
                    dataIndex: 'status',
                    width: 80,
                    render: (s: ReportStatus) => (
                      <Tag color={STATUS_COLORS[s]}>{s}</Tag>
                    ),
                  },
                  {
                    title: '评分',
                    dataIndex: 'overall_score',
                    width: 70,
                    render: (score: number | null) =>
                      score !== null ? (
                        <Badge
                          count={score.toFixed(1)}
                          color={
                            score >= 4
                              ? '#52c41a'
                              : score >= 3
                                ? '#faad14'
                                : '#ff4d4f'
                          }
                        />
                      ) : (
                        <Text type="secondary">—</Text>
                      ),
                  },
                  {
                    title: '建议',
                    dataIndex: 'recommendation',
                    width: 70,
                    render: (rec: Recommendation | null) =>
                      rec ? <Tag color={REC_COLORS[rec]}>{rec}</Tag> : null,
                  },
                  {
                    title: '时间',
                    dataIndex: 'created_at',
                    width: 120,
                    render: (ts: string | null) =>
                      ts ? new Date(ts).toLocaleDateString('zh-CN') : null,
                  },
                  {
                    title: '操作',
                    width: 90,
                    render: (_: unknown, r: ResearchReportSummary) =>
                      (r.status === 'failed' || r.status === 'rejected') && (
                        <Button
                          type="link"
                          size="small"
                          icon={<RedoOutlined />}
                          loading={retryMutation.isPending && retryMutation.variables === r.stock_code}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleRetry(r.stock_code);
                          }}
                        >
                          重试
                        </Button>
                      ),
                  },
                ]}
              />
            )}
          </PageSection>
        </Col>

        {/* Right: Selected Report Detail */}
        <Col span={14}>
          <PageSection title="报告详情">
            {!selectedReport ? (
              <Card>
                <Empty description="点击左侧报告查看详情" />
              </Card>
            ) : reportDetailQuery.isLoading ? (
              <Card>
                <Space style={{ width: '100%', justifyContent: 'center', padding: 24 }}>
                  <Text type="secondary">加载报告详情...</Text>
                </Space>
              </Card>
            ) : (
              <ReportDetail
                report={selectedReport}
                retrying={retryMutation.isPending && retryMutation.variables === selectedReport.stock_code}
                onRetry={() => handleRetry(selectedReport.stock_code)}
              />
            )}
          </PageSection>
        </Col>
      </Row>
    </div>
  );
}

// ── Report Detail component ──────────────────────────────────────────────

function ReportDetail({
  report,
  retrying,
  onRetry,
}: {
  report: ResearchReportFull;
  retrying: boolean;
  onRetry: () => void;
}) {
  const canRetry = report.status === 'failed' || report.status === 'rejected';

  return (
    <Card>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        {/* Header */}
        <div>
          <h3 style={{ marginBottom: 4 }}>
            <Link to={`/stock/${report.stock_code}`}>
              {report.stock_code}
              {report.stock_name && (
                <span style={{ color: 'var(--gray-500)', marginLeft: 8, fontWeight: 400, fontSize: 'var(--fs-base)' }}>
                  {report.stock_name}
                </span>
              )}
            </Link>
            <Tag
              color={STATUS_COLORS[report.status]}
              style={{ marginLeft: 12 }}
            >
              {report.status}
            </Tag>
          </h3>
          <Space size="middle" wrap>
            <Tag>{PIPELINE_LABELS[report.pipeline_type] ?? report.pipeline_type}</Tag>
            {report.recommendation && (
              <Tag color={REC_COLORS[report.recommendation]}>
                {report.recommendation}
              </Tag>
            )}
            {report.evidence_grade && (
              <Tag color={report.evidence_grade === 'A' ? 'success' : report.evidence_grade === 'B' ? 'warning' : 'default'}>
                证据 {report.evidence_grade}
              </Tag>
            )}
            {report.overall_score !== null && (
              <Text strong>评分 {report.overall_score.toFixed(1)}</Text>
            )}
            {/* Retry button for failed/rejected reports */}
            {canRetry && (
              <Button
                type="primary"
                danger
                size="small"
                icon={<RedoOutlined />}
                loading={retrying}
                onClick={(e) => {
                  e.stopPropagation();
                  onRetry();
                }}
              >
                重新研究
              </Button>
            )}
          </Space>
        </div>

        {/* Conflicts warning */}
        {report.data_conflict && report.data_conflict.length > 0 && (
          <Alert
            type="warning"
            message={`发现 ${report.data_conflict.length} 项数据冲突`}
            description={report.data_conflict
              .map(
                (c) =>
                  `${c.field}: LLM=${c.llm_value} vs DB=${c.db_value} (差 ${c.diff_pct}%)`,
              )
              .join('；')}
            showIcon
          />
        )}

        {/* Red line warning */}
        {report.red_line_hit && report.red_line_hit.length > 0 && (
          <Alert
            type="error"
            message={`触发 ${report.red_line_hit.length} 条红线`}
            description={report.red_line_hit
              .map((r) => `${r.red_line_type}: ${r.action_taken}`)
              .join('；')}
            showIcon
          />
        )}

        {/* Markdown body */}
        <div
          className="markdown-report"
          style={{
            background: '#fafafa',
            padding: 16,
            borderRadius: 6,
            maxHeight: '70vh',
            overflow: 'auto',
          }}
        >
          {report.markdown_output ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{report.markdown_output}</ReactMarkdown>
          ) : (
            <Empty description="无 markdown 报告" />
          )}
        </div>

        {/* Metadata */}
        <Text type="secondary" style={{ fontSize: 12 }}>
          生成时间: {report.created_at ? new Date(report.created_at).toLocaleString('zh-CN') : '?'}
          {report.expires_at && (
            <>{'　·　'}过期: {new Date(report.expires_at).toLocaleString('zh-CN')}</>
          )}
          {report.prompt_version && <>{'　·　'}Prompt: {report.prompt_version}</>}
        </Text>
      </Space>
    </Card>
  );
}
