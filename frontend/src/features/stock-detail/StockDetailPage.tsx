import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Card,
  Empty,
  Radio,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  ArrowLeftOutlined,
  ExperimentOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';

import {
  getLatestReport,
  getReportHistory,
  triggerResearch,
  type GLMTier,
  type ResearchReportFull,
} from '../../api/research';
import PageHeader from '../../components/primitives/PageHeader';
import PageSection from '../../components/primitives/PageSection';

const { Text, Title } = Typography;

export default function StockDetailPage() {
  const { code = '' } = useParams<{ code: string }>();
  const queryClient = useQueryClient();
  const [tier, setTier] = useState<GLMTier>('sonnet');
  const [useWebSearch, setUseWebSearch] = useState(true);

  const latestQuery = useQuery({
    queryKey: ['research', 'latest', code],
    queryFn: () => getLatestReport(code),
    enabled: !!code,
  });

  const historyQuery = useQuery({
    queryKey: ['research', 'history', code],
    queryFn: () => getReportHistory(code, 20),
    enabled: !!code,
  });

  const triggerMutation = useMutation({
    mutationFn: (params: { force: boolean }) =>
      triggerResearch(code, {
        model_tier: tier,
        use_web_search: useWebSearch,
        force: params.force,
      }),
    onSuccess: (data) => {
      message.success(`${code} 研究完成：评分 ${data.overall_score} / ${data.recommendation}`);
      queryClient.invalidateQueries({ queryKey: ['research', 'latest', code] });
      queryClient.invalidateQueries({ queryKey: ['research', 'history', code] });
      queryClient.invalidateQueries({ queryKey: ['research', 'health'] });
      queryClient.invalidateQueries({ queryKey: ['research', 'reports'] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'unknown error';
      message.error(`研究失败：${msg}`);
    },
  });

  if (!code) {
    return <Empty description="未指定股票代码" />;
  }

  const latest = latestQuery.data;
  const isLoading = latestQuery.isLoading || triggerMutation.isPending;

  return (
    <div>
      <PageHeader
        title={
          <Space>
            <Link to="/universe">
              <Button type="text" icon={<ArrowLeftOutlined />} />
            </Link>
            <span>{code}</span>
            {latest?.recommendation && (
              <Tag color={latest.recommendation === 'BUY' ? 'success' : latest.recommendation === 'PASS' ? 'default' : 'warning'}>
                {latest.recommendation}
              </Tag>
            )}
          </Space>
        }
        enLabel="Stock Detail"
        purpose="深度研究 · 4 大师并行 · ai-berkshire 风格报告"
      />

      {/* ── Trigger Research Card ────────────────────────────────── */}
      <PageSection title="触发研究">
        <Card>
          <Space wrap>
            <Text>模型层：</Text>
            <Select<GLMTier>
              value={tier}
              onChange={setTier}
              style={{ width: 180 }}
              options={[
                { label: 'GLM 5.1 (Sonnet 等价，默认)', value: 'sonnet' },
                { label: 'GLM 5.2 (Opus 等价，最贵最好)', value: 'opus' },
                { label: 'GLM 4.8 (Haiku 等价，最便宜)', value: 'haiku' },
              ]}
            />
            <Text>Web 搜索：</Text>
            <Radio.Group
              value={useWebSearch ? 'on' : 'off'}
              onChange={(e) => setUseWebSearch(e.target.value === 'on')}
            >
              <Radio.Button value="on">开启（推荐）</Radio.Button>
              <Radio.Button value="off">关闭（降级）</Radio.Button>
            </Radio.Group>
          </Space>

          <div style={{ marginTop: 16 }}>
            <Space>
              <Button
                type="primary"
                icon={<ThunderboltOutlined />}
                loading={triggerMutation.isPending}
                onClick={() => triggerMutation.mutate({ force: false })}
              >
                触发研究（30 天缓存）
              </Button>
              <Button
                icon={<ExperimentOutlined />}
                loading={triggerMutation.isPending}
                onClick={() => triggerMutation.mutate({ force: true })}
                danger
              >
                强制重跑（bypass 30 天缓存）
              </Button>
            </Space>
          </div>

          <div style={{ marginTop: 12 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              决策 6（redesign-decisions-v2）：6 LLM 调用/家（data_collect + 4 masters + synthesis）。
              单次成本预估：Sonnet ~$0.028 / Opus ~$0.11 / Haiku ~$0.001。
              受 $150/月硬熔断保护。
            </Text>
          </div>
        </Card>
      </PageSection>

      {/* ── Latest Report ────────────────────────────────────────── */}
      <PageSection title="最新报告">
        <Card>
          {isLoading ? (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <Spin tip="研究中... 通常需要 30-60 秒" size="large" />
            </div>
          ) : latest ? (
            <ReportView report={latest} />
          ) : (
            <Empty
              description={
                <Space direction="vertical">
                  <Text type="secondary">还没有研究报告</Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    点击上方「触发研究」按钮开始
                  </Text>
                </Space>
              }
            />
          )}
        </Card>
      </PageSection>

      {/* ── History ──────────────────────────────────────────────── */}
      <PageSection title={`历史研究 (${historyQuery.data?.length ?? 0})`}>
        <Card>
          {(historyQuery.data ?? []).length === 0 ? (
            <Text type="secondary">无历史</Text>
          ) : (
            <Space direction="vertical" style={{ width: '100%' }}>
              {(historyQuery.data ?? []).map((r) => (
                <Card
                  key={r.id}
                  size="small"
                  style={{ background: '#fafafa' }}
                >
                  <Space>
                    <strong>{new Date(r.created_at ?? '').toLocaleString('zh-CN')}</strong>
                    <Tag>{r.pipeline_type}</Tag>
                    {r.overall_score !== null && (
                      <Tag color={r.overall_score >= 4 ? 'success' : r.overall_score >= 3 ? 'warning' : 'error'}>
                        {r.overall_score.toFixed(1)}
                      </Tag>
                    )}
                    {r.recommendation && <Tag>{r.recommendation}</Tag>}
                    {r.evidence_grade && <Tag>证据 {r.evidence_grade}</Tag>}
                    <Tag color={r.status === 'completed' ? 'success' : r.status === 'rejected' ? 'error' : 'warning'}>
                      {r.status}
                    </Tag>
                  </Space>
                </Card>
              ))}
            </Space>
          )}
        </Card>
      </PageSection>
    </div>
  );
}

function ReportView({ report }: { report: ResearchReportFull }) {
  return (
    <div>
      {/* Header */}
      <Space style={{ marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          {report.stock_code}
        </Title>
        {report.recommendation && (
          <Tag color={report.recommendation === 'BUY' ? 'success' : report.recommendation === 'PASS' ? 'default' : 'warning'}>
            {report.recommendation}
          </Tag>
        )}
        {report.overall_score !== null && (
          <Tag color={report.overall_score >= 4 ? 'success' : report.overall_score >= 3 ? 'warning' : 'error'}>
            {report.overall_score.toFixed(1)} / 5
          </Tag>
        )}
        {report.evidence_grade && (
          <Tag>证据 {report.evidence_grade}</Tag>
        )}
        <Tag>{report.pipeline_type}</Tag>
      </Space>

      {/* Conflicts */}
      {report.data_conflict && report.data_conflict.length > 0 && (
        <Alert
          style={{ marginBottom: 12 }}
          type="warning"
          message={`${report.data_conflict.length} 项数据冲突`}
          description={report.data_conflict
            .map((c) => `${c.field}: LLM=${c.llm_value} vs DB=${c.db_value} (${c.diff_pct}%)`)
            .join('；')}
          showIcon
        />
      )}

      {/* Red lines */}
      {report.red_line_hit && report.red_line_hit.length > 0 && (
        <Alert
          style={{ marginBottom: 12 }}
          type="error"
          message={`${report.red_line_hit.length} 条红线触发`}
          description={report.red_line_hit
            .map((r) => `${r.red_line_type}: ${r.action_taken}`)
            .join('；')}
          showIcon
        />
      )}

      {/* Markdown */}
      {report.markdown_output ? (
        <div
          style={{
            background: '#fafafa',
            padding: 16,
            borderRadius: 6,
            maxHeight: '60vh',
            overflow: 'auto',
          }}
        >
          <ReactMarkdown>{report.markdown_output}</ReactMarkdown>
        </div>
      ) : (
        <Empty description="无 markdown 报告" />
      )}

      <div style={{ marginTop: 12 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          生成: {report.created_at ? new Date(report.created_at).toLocaleString('zh-CN') : '?'}
          {report.expires_at && (
            <> · 30 天缓存至 {new Date(report.expires_at).toLocaleDateString('zh-CN')}</>
          )}
          {report.prompt_version && <> · Prompt {report.prompt_version}</>}
        </Text>
      </div>
    </div>
  );
}
