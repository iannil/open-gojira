import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Button,
  Card,
  Col,
  Input,
  List,
  Modal,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  ApiOutlined,
  CheckCircleOutlined,
  FileTextOutlined,
  ReloadOutlined,
  RightOutlined,
  SearchOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';

import {
  listLifecycleStocks,
  listThemeScanReports,
  getThemeScanReport,
  triggerThemeScan,
  triggerBatchResearch,
} from '../../api/client';
import type { ThemeScanSummary } from '../../api/client';
import { getResearchHealth } from '../../api/research';
import PageHeader from '../../components/primitives/PageHeader';
import QueryBoundary from '../../components/QueryBoundary';

const { Text } = Typography;

const FUNNEL: { key: string; label: string }[] = [
  { key: 'universe', label: 'universe' },
  { key: 'watchlist', label: 'watchlist' },
  { key: 'researched', label: 'researched' },
  { key: 'candidate', label: 'candidate' },
  { key: 'holding', label: 'holding' },
  { key: 'exited', label: 'exited' },
];

const STATE_COLOR: Record<string, string> = {
  universe: 'default',
  watchlist: 'blue',
  researched: 'cyan',
  candidate: 'geekblue',
  signaled: 'orange',
  holding: 'green',
  exited: 'default',
};

// ── Left Panel: quality_screen ────────────────────────────────────

function QualityScreenPanel({ onNavigateToStock }: { onNavigateToStock: (code: string) => void }) {
  const queryClient = useQueryClient();
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set());

  const healthQuery = useQuery({
    queryKey: ['research', 'health'],
    queryFn: getResearchHealth,
    refetchInterval: 60_000,
    select: (d) => d ?? { spend: null as any, lifecycle_counts: {} as Record<string, number> },
  });

  const lifecycleQuery = useQuery({
    queryKey: ['stocks', 'lifecycle', 'watchlist'],
    queryFn: () => listLifecycleStocks('watchlist', 100),
    refetchInterval: 60_000,
  });

  const counts = (healthQuery.data as any)?.lifecycle_counts ?? {};

  const batchResearchM = useMutation({
    mutationFn: (codes: string[]) =>
      triggerBatchResearch({
        stock_codes: codes,
        source: 'quality_screen',
      }),
    onSuccess: (data) => {
      message.success(
        `批量深度研究已提交：${data.triggered_count} 个触发，${data.skipped_count} 个跳过`,
      );
      setSelectedCodes(new Set());
      queryClient.invalidateQueries({ queryKey: ['research', 'health'] });
    },
    onError: (err: unknown) => {
      message.error(`批量提交失败：${err instanceof Error ? err.message : '未知错误'}`);
    },
  });

  const handleBatchResearch = useCallback(() => {
    if (selectedCodes.size === 0) {
      message.warning('请先选择股票');
      return;
    }
    Modal.confirm({
      title: `确认对 ${selectedCodes.size} 只股票发起深度研究？`,
      content: `这将消耗 LLM 预算。每只股票约需 30-60 秒。`,
      onOk: () => batchResearchM.mutate(Array.from(selectedCodes)),
    });
  }, [selectedCodes, batchResearchM]);

  const columns = [
    {
      title: '代码',
      dataIndex: 'stock_code',
      key: 'stock_code',
      width: 90,
      render: (code: string) => (
        <a onClick={() => onNavigateToStock(code)} style={{ fontFamily: 'monospace' }}>
          {code}
        </a>
      ),
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 100,
    },
    {
      title: '行业',
      dataIndex: 'industry',
      key: 'industry',
      width: 120,
      render: (v: string | null) => v ?? '—',
    },
    {
      title: '进入时间',
      dataIndex: 'entered_state_at',
      key: 'entered_state_at',
      width: 100,
      render: (v: string | null) => (v ? new Date(v).toLocaleDateString('zh-CN') : '—'),
    },
  ];

  return (
    <Card
      title={
        <Space>
          <CheckCircleOutlined style={{ color: '#52c41a' }} />
          <span>价值复利引擎 · quality_screen</span>
        </Space>
      }
      styles={{ body: { padding: 16 } }}
    >
      {/* Lifecycle Funnel */}
      <Card
        size="small"
        title="股票生命周期漏斗"
        style={{ marginBottom: 16 }}
        extra={
          <Text type="secondary" style={{ fontSize: 12 }}>
            最后更新：{healthQuery.dataUpdatedAt ? new Date(healthQuery.dataUpdatedAt).toLocaleTimeString('zh-CN') : '—'}
          </Text>
        }
      >
        <Row gutter={[8, 8]} justify="center" align="middle">
          {FUNNEL.map((item, idx) => (
            <Col key={item.key}>
              <div style={{ textAlign: 'center', minWidth: 60 }}>
                <Statistic
                  value={counts[item.key] ?? 0}
                  valueStyle={{ fontSize: 20, fontWeight: 600 }}
                />
                <Tag color={STATE_COLOR[item.key] ?? 'default'} style={{ marginTop: 4 }}>
                  {item.label}
                </Tag>
              </div>
              {idx < FUNNEL.length - 1 && (
                <div style={{ textAlign: 'center', color: '#D6D3D1', fontSize: 18, marginTop: 16 }}>
                  <RightOutlined />
                </div>
              )}
            </Col>
          ))}
        </Row>
      </Card>

      {/* Watchlist Stocks */}
      <QueryBoundary query={lifecycleQuery} isEmpty={(d) => d.length === 0}>
        {(watchlistStocks) => (<div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <Text strong>
              观察池股票
              <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                {watchlistStocks.length} 只
              </Text>
            </Text>
            <Space>
              <Button
                size="small"
                icon={<ReloadOutlined />}
                onClick={() => lifecycleQuery.refetch()}
              >
                刷新
              </Button>
              <Button
                size="small"
                type="primary"
                icon={<ThunderboltOutlined />}
                onClick={handleBatchResearch}
                loading={batchResearchM.isPending}
                disabled={selectedCodes.size === 0}
              >
                一键深研 ({selectedCodes.size})
              </Button>
            </Space>
          </div>
          <Table
            dataSource={watchlistStocks}
            columns={columns}
            rowKey="stock_code"
            size="small"
            pagination={{ pageSize: 15, showSizeChanger: false }}
            rowSelection={{
              type: 'checkbox',
              selectedRowKeys: Array.from(selectedCodes),
              onChange: (keys) => setSelectedCodes(new Set(keys as string[])),
            }}
            locale={{ emptyText: '暂无通过质量筛选的股票' }}
          />
        </div>)}
      </QueryBoundary>
    </Card>
  );
}

// ── Right Panel: theme_scan ───────────────────────────────────────

function ThemeScanPanel({ onNavigateToStock }: { onNavigateToStock: (code: string) => void }) {
  const queryClient = useQueryClient();
  const [selectedReportId, setSelectedReportId] = useState<number | null>(null);
  const [themeInput, setThemeInput] = useState('');
  const [candidateCodes, setCandidateCodes] = useState<Set<string>>(new Set());

  const reportsQuery = useQuery({
    queryKey: ['theme-scan', 'reports'],
    queryFn: () => listThemeScanReports(20),
    refetchInterval: 60_000,
  });

  const reportDetailQuery = useQuery({
    queryKey: ['theme-scan', 'report', selectedReportId],
    queryFn: () => getThemeScanReport(selectedReportId!),
    enabled: selectedReportId !== null,
  });

  const triggerM = useMutation({
    mutationFn: () =>
      triggerThemeScan({
        theme: themeInput.trim(),
        model_tier: 'sonnet',
        use_web_search: true,
      }),
    onSuccess: (data) => {
      message.success(`主题扫描「${themeInput.trim()}」已启动，报告 ID: ${data.id}`);
      setThemeInput('');
      queryClient.invalidateQueries({ queryKey: ['theme-scan', 'reports'] });
    },
    onError: (err: unknown) => {
      message.error(`扫描失败：${err instanceof Error ? err.message : '未知错误'}`);
    },
  });

  const batchResearchM = useMutation({
    mutationFn: (codes: string[]) =>
      triggerBatchResearch({
        stock_codes: codes,
        source: 'theme_scan',
      }),
    onSuccess: (data) => {
      message.success(
        `批量深度研究已提交：${data.triggered_count} 个触发，${data.skipped_count} 个跳过`,
      );
      setCandidateCodes(new Set());
    },
    onError: (err: unknown) => {
      message.error(`批量提交失败：${err instanceof Error ? err.message : '未知错误'}`);
    },
  });

  const handleBatchResearch = useCallback(() => {
    if (candidateCodes.size === 0) {
      message.warning('请先选择候选股票');
      return;
    }
    Modal.confirm({
      title: `确认对 ${candidateCodes.size} 只候选股票发起深度研究？`,
      content: `将 source=theme_scan 传入，消耗 LLM 预算。`,
      onOk: () => batchResearchM.mutate(Array.from(candidateCodes)),
    });
  }, [candidateCodes, batchResearchM]);

  const selectedReport = reportDetailQuery.data;
  const candidates: Array<{ code: string; name: string; layer: string; scarcity_score: number; thesis: string }> =
    (selectedReport?.ranked_candidates as any[])?.map((c: any) => ({
      code: c.code ?? c.stock_code ?? '',
      name: c.name ?? '',
      layer: c.layer ?? '',
      scarcity_score: c.scarcity_score ?? 0,
      thesis: c.thesis ?? '',
    })) ?? [];

  return (
    <Card
      title={
        <Space>
          <ApiOutlined style={{ color: '#722ed1' }} />
          <span>产业链卡点引擎 · theme_scan</span>
        </Space>
      }
      styles={{ body: { padding: 16 } }}
    >
      {/* Trigger New Scan */}
      <Card size="small" title="发起新扫描" style={{ marginBottom: 16 }}>
        <Space style={{ width: '100%' }}>
          <Input
            placeholder="输入主题，例如：HBM存储器、人形机器人丝杠"
            value={themeInput}
            onChange={(e) => setThemeInput(e.target.value)}
            onPressEnter={() => themeInput.trim() && triggerM.mutate()}
            style={{ flex: 1 }}
          />
          <Button
            type="primary"
            icon={<SearchOutlined />}
            onClick={() => triggerM.mutate()}
            loading={triggerM.isPending}
            disabled={!themeInput.trim()}
          >
            扫描
          </Button>
        </Space>
      </Card>

      {/* Reports List */}
      <QueryBoundary query={reportsQuery} isEmpty={(d) => d.length === 0}>
        {(reports) => (<div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <Text strong>历史扫描报告</Text>
            <Button size="small" icon={<ReloadOutlined />} onClick={() => reportsQuery.refetch()}>
              刷新
            </Button>
          </div>
          <List
            dataSource={reports.slice(0, 10)}
            size="small"
            locale={{ emptyText: '暂无主题扫描记录' }}
            renderItem={(item: ThemeScanSummary) => (
              <List.Item
                onClick={() => setSelectedReportId(item.id)}
                style={{
                  cursor: 'pointer',
                  background: selectedReportId === item.id ? '#F5F5F4' : undefined,
                  padding: '8px 12px',
                }}
                extra={
                  <Space>
                    <Tag color={item.status === 'completed' ? 'success' : 'warning'}>
                      {item.status}
                    </Tag>
                    {item.evidence_grade && <Tag>{item.evidence_grade}</Tag>}
                  </Space>
                }
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <FileTextOutlined />
                      <Text strong>{item.theme}</Text>
                    </Space>
                  }
                  description={
                    item.created_at
                      ? new Date(item.created_at).toLocaleString('zh-CN')
                      : undefined
                  }
                />
              </List.Item>
            )}
          />
        </div>)}
      </QueryBoundary>

      {/* Selected Report Detail */}
      {selectedReport && candidates.length > 0 && (
        <Card
          size="small"
          title={
            <Space>
              <span>候选股票：{selectedReport.theme}</span>
              {candidateCodes.size > 0 && (
                <Button
                  size="small"
                  type="primary"
                  icon={<ThunderboltOutlined />}
                  onClick={handleBatchResearch}
                  loading={batchResearchM.isPending}
                >
                  一键深研 ({candidateCodes.size})
                </Button>
              )}
            </Space>
          }
          style={{ marginTop: 12 }}
        >
          {candidates.map((c) => (
            <div
              key={c.code}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '6px 8px',
                cursor: 'pointer',
                borderRadius: 4,
                background: candidateCodes.has(c.code) ? '#F0F5FF' : undefined,
              }}
              onClick={() => {
                const next = new Set(candidateCodes);
                if (next.has(c.code)) next.delete(c.code);
                else next.add(c.code);
                setCandidateCodes(next);
              }}
            >
              <Space>
                <a onClick={(e) => { e.stopPropagation(); onNavigateToStock(c.code); }} style={{ fontFamily: 'monospace' }}>
                  {c.code}
                </a>
                <Text>{c.name}</Text>
                <Tag color="purple">{c.layer}</Tag>
              </Space>
              <Space>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  稀缺分: {c.scarcity_score?.toFixed(1)}
                </Text>
                {candidateCodes.has(c.code) && <CheckCircleOutlined style={{ color: '#1890ff' }} />}
              </Space>
            </div>
          ))}
        </Card>
      )}
    </Card>
  );
}

// ── Main Page ─────────────────────────────────────────────────────

export default function EnginePage() {
  const navigate = useNavigate();

  const handleNavigateToStock = useCallback(
    (code: string) => navigate(`/stock/${code}`),
    [navigate],
  );

  return (
    <div>
      <PageHeader
        title="双引擎选股"
        enLabel="Dual Engine"
        purpose="价值复利（quality_screen）+ 产业链卡点（theme_scan）—— 两条独立选股来源，不互相裁决"
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <QualityScreenPanel onNavigateToStock={handleNavigateToStock} />
        </Col>
        <Col xs={24} lg={12}>
          <ThemeScanPanel onNavigateToStock={handleNavigateToStock} />
        </Col>
      </Row>
    </div>
  );
}
