import { useState, useCallback, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Button,
  Col,
  Input,
  List,
  Modal,
  Row,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import {
  BugOutlined,
  CheckCircleFilled,
  CheckCircleOutlined,
  FileTextOutlined,
  ReloadOutlined,
  RightOutlined,
  SearchOutlined,
  ThunderboltOutlined,
  WarningOutlined,
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

// ── Design Tokens ─────────────────────────────────────────────────

const COLORS = {
  // Left panel — value engine (ink blue)
  ink: { primary: '#1E3A5F', light: '#F0F4F9', border: '#D6E3F0', icon: '#1E3A5F' },
  // Right panel — chain engine (jade teal)
  jade: { primary: '#0D5E4A', light: '#F2F8F6', border: '#C5E5DD', icon: '#0D5E4A' },
  // Funnel stages — cool → warm progression
  funnel: {
    universe: { bg: '#F1F5F9', text: '#475569', border: '#E2E8F0' },
    watchlist: { bg: '#DBEAFE', text: '#1E40AF', border: '#BFDBFE' },
    researched: { bg: '#CFFAFE', text: '#155E75', border: '#A5F3FC' },
    candidate: { bg: '#E0E7FF', text: '#3730A3', border: '#C7D2FE' },
    signaled: { bg: '#FEF3C7', text: '#92400E', border: '#FDE68A' },
    holding: { bg: '#DCFCE7', text: '#166534', border: '#BBF7D0' },
    exited: { bg: '#F3F4F6', text: '#9CA3AF', border: '#E5E7EB' },
  },
  signal: { red: '#DC2626', amber: '#D97706', green: '#16A34A' },
};

// ── Funnel Configuration ──────────────────────────────────────────

interface FunnelStageDef {
  key: string;
  label: string;
  labelCn: string;
  tooltip: string;
}

const FUNNEL: FunnelStageDef[] = [
  { key: 'universe', label: 'Universe', labelCn: '全量池', tooltip: '全 A 股标的' },
  { key: 'watchlist', label: 'Watchlist', labelCn: '观察池', tooltip: '通过质量筛选' },
  { key: 'researched', label: 'Researched', labelCn: '已深研', tooltip: '完成 LLM 深度研究' },
  { key: 'candidate', label: 'Candidate', labelCn: '候选池', tooltip: '通过评分审核' },
  { key: 'holding', label: 'Holding', labelCn: '持仓', tooltip: '当前持仓' },
  { key: 'exited', label: 'Exited', labelCn: '已退出', tooltip: '已卖出或放弃' },
];

const funnelColor = (stage: string) =>
  (COLORS.funnel as Record<string, { bg: string; text: string; border: string }>)[stage] ?? COLORS.funnel.universe;

// ── Funnel Stage Component ────────────────────────────────────────

function FunnelPill({
  stage,
  count,
  bottleneck,
}: {
  stage: FunnelStageDef;
  count: number;
  bottleneck: boolean;
}) {
  const c = funnelColor(stage.key);
  return (
    <Tooltip title={stage.tooltip}>
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          minWidth: 80,
          position: 'relative',
        }}
      >
        <div
          style={{
            background: c.bg,
            border: `1px solid ${c.border}`,
            borderRadius: 12,
            padding: '10px 16px',
            textAlign: 'center',
            minWidth: 72,
            position: 'relative',
          }}
        >
          <div
            style={{
              fontFamily: 'var(--font-mono, "JetBrains Mono", monospace)',
              fontSize: 26,
              fontWeight: 700,
              lineHeight: 1.2,
              color: c.text,
            }}
          >
            {count.toLocaleString()}
          </div>
          <div
            style={{
              fontSize: 11,
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              color: c.text,
              opacity: 0.75,
              marginTop: 2,
            }}
          >
            {stage.label}
          </div>
          {bottleneck && (
            <Tooltip title="此处降幅最大 — 可能为瓶颈">
              <WarningOutlined
                style={{
                  position: 'absolute',
                  top: -6,
                  right: -6,
                  color: COLORS.signal.amber,
                  fontSize: 14,
                }}
              />
            </Tooltip>
          )}
        </div>
      </div>
    </Tooltip>
  );
}

// ── Funnel Arrow ──────────────────────────────────────────────────

function FunnelArrow({ conversion }: { conversion: number | null }) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '0 4px',
        minWidth: 40,
        color: '#D6D3D1',
      }}
    >
      <RightOutlined style={{ fontSize: 20, color: '#D6D3D1' }} />
      {conversion != null && (
        <span
          style={{
            fontSize: 10,
            color: conversion < 10 ? COLORS.signal.amber : '#78716C',
            fontWeight: conversion < 10 ? 600 : 400,
            marginTop: 2,
            whiteSpace: 'nowrap',
          }}
        >
          {conversion.toFixed(1)}%
        </span>
      )}
    </div>
  );
}

// ── Funnel Section ────────────────────────────────────────────────

function FunnelSection({ counts }: { counts: Record<string, number> }) {
  // Find bottleneck: stage with the largest relative drop from previous
  let bottleneckIdx = -1;
  let maxDrop = 0;
  const stages = FUNNEL;
  for (let i = 1; i < stages.length; i++) {
    const prev = counts[stages[i - 1].key] ?? 0;
    const curr = counts[stages[i].key] ?? 0;
    if (prev > 0) {
      const drop = (prev - curr) / prev;
      if (drop > maxDrop) {
        maxDrop = drop;
        bottleneckIdx = i;
      }
    }
  }

  return (
    <div
      style={{
        background: 'linear-gradient(135deg, #F8FAFC 0%, #F1F5F9 100%)',
        borderRadius: 12,
        padding: '20px 16px',
        border: '1px solid #E2E8F0',
        marginBottom: 16,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexWrap: 'nowrap',
          overflow: 'auto',
          paddingBottom: 4,
        }}
      >
        {stages.map((stage, idx) => (
          <div key={stage.key} style={{ display: 'flex', alignItems: 'center' }}>
            <FunnelPill
              stage={stage}
              count={counts[stage.key] ?? 0}
              bottleneck={idx === bottleneckIdx && bottleneckIdx > 0}
            />
            {idx < stages.length - 1 && (
              <FunnelArrow
                conversion={
                  idx > 0
                    ? (() => {
                        const curr = counts[stage.key] ?? 0;
                        const next = counts[stages[idx + 1].key] ?? 0;
                        return curr > 0 ? (next / curr) * 100 : null;
                      })()
                    : (() => {
                        const first = counts[stages[0].key] ?? 0;
                        const second = counts[stages[1].key] ?? 0;
                        return first > 0 ? (second / first) * 100 : null;
                      })()
                }
              />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Left Panel: quality_screen ────────────────────────────────────

function QualityScreenPanel({
  onNavigateToStock,
}: {
  onNavigateToStock: (code: string) => void;
}) {
  const queryClient = useQueryClient();
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set());

  const healthQuery = useQuery({
    queryKey: ['research', 'health'],
    queryFn: getResearchHealth,
    refetchInterval: 60_000,
    select: (d) =>
      d ?? {
        spend: null as any,
        lifecycle_counts: {} as Record<string, number>,
      },
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
      message.error(
        `批量提交失败：${err instanceof Error ? err.message : '未知错误'}`,
      );
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
      width: 100,
      render: (code: string) => (
        <a
          onClick={() => onNavigateToStock(code)}
          style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: 13 }}
        >
          {code}
        </a>
      ),
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 100,
      render: (v: string) => (
        <Text style={{ fontWeight: 500 }}>{v}</Text>
      ),
    },
    {
      title: '行业',
      dataIndex: 'industry',
      key: 'industry',
      width: 130,
      render: (v: string | null) =>
        v ? (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {v}
          </Text>
        ) : (
          '—'
        ),
    },
    {
      title: '进入时间',
      dataIndex: 'entered_state_at',
      key: 'entered_state_at',
      width: 110,
      render: (v: string | null) =>
        v ? (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {new Date(v).toLocaleDateString('zh-CN')}
          </Text>
        ) : (
          '—'
        ),
    },
    {
      title: '最后深研',
      dataIndex: 'last_research_at',
      key: 'last_research_at',
      width: 130,
      render: (v: string | null) =>
        v ? (
          <Tooltip title={new Date(v).toLocaleString('zh-CN')}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {new Date(v).toLocaleDateString('zh-CN')}
            </Text>
          </Tooltip>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>—</Text>
        ),
    },
  ];

  return (
    <div
      style={{
        borderLeft: `3px solid ${COLORS.ink.primary}`,
        background: COLORS.ink.light,
        borderRadius: 8,
        padding: 16,
        minHeight: '100%',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginBottom: 16,
        }}
      >
        <CheckCircleFilled style={{ color: COLORS.ink.icon, fontSize: 20 }} />
        <div>
          <Text strong style={{ fontSize: 15, color: COLORS.ink.primary }}>
            价值复利引擎
          </Text>
          <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
            quality_screen
          </Text>
        </div>
      </div>

      {/* Funnel */}
      <FunnelSection counts={counts} />

      {/* Watchlist Stocks */}
      <QueryBoundary
        query={lifecycleQuery}
        isEmpty={(d) => d.length === 0}
      >
        {(watchlistStocks) => (
          <div
            style={{
              background: '#fff',
              borderRadius: 8,
              border: '1px solid #E2E8F0',
              padding: 12,
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 8,
              }}
            >
              <Text strong style={{ fontSize: 13 }}>
                观察池
                <Text
                  type="secondary"
                  style={{ marginLeft: 6, fontSize: 12 }}
                >
                  {watchlistStocks.length} 只
                </Text>
              </Text>
              <Space size={4}>
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
                  style={{ background: COLORS.ink.primary }}
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
          </div>
        )}
      </QueryBoundary>
    </div>
  );
}

// ── Right Panel: theme_scan ───────────────────────────────────────

function ThemeScanPanel({
  onNavigateToStock,
}: {
  onNavigateToStock: (code: string) => void;
}) {
  const queryClient = useQueryClient();
  const [selectedReportId, setSelectedReportId] = useState<number | null>(
    null,
  );
  const [themeInput, setThemeInput] = useState('');
  const [candidateCodes, setCandidateCodes] = useState<Set<string>>(
    new Set(),
  );

  const reportsQuery = useQuery({
    queryKey: ['theme-scan', 'reports'],
    queryFn: () => listThemeScanReports(20),
    refetchInterval: 60_000,
  });

  const reportDetailQuery = useQuery({
    queryKey: ['theme-scan', 'report', selectedReportId],
    queryFn: () => getThemeScanReport(selectedReportId!),
    enabled: selectedReportId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'running' ? 3000 : false;
    },
  });

  const prevStatusRef = useRef<string | null>(null);
  useEffect(() => {
    const current = reportDetailQuery.data?.status;
    const prev = prevStatusRef.current;
    prevStatusRef.current = current ?? null;

    if (prev === 'running' && current && current !== 'running') {
      if (current === 'completed') {
        message.success(
          `主题扫描「${reportDetailQuery.data?.theme}」已完成`,
        );
      } else if (current === 'empty') {
        message.info('扫描完成，但未找到有效的 A 股候选标的');
      } else if (current === 'failed') {
        message.error('主题扫描失败，请查看服务端日志');
      }
      queryClient.invalidateQueries({ queryKey: ['theme-scan', 'reports'] });
    }
  }, [reportDetailQuery.data?.status, reportDetailQuery.data?.theme, queryClient]);

  const triggerM = useMutation({
    mutationFn: () =>
      triggerThemeScan({
        theme: themeInput.trim(),
        model_tier: 'sonnet',
        use_web_search: true,
      }),
    onSuccess: (data) => {
      message.success(
        `主题扫描「${themeInput.trim()}」已提交，ID: ${data.id}`,
      );
      setThemeInput('');
      setSelectedReportId(data.id);
      queryClient.invalidateQueries({ queryKey: ['theme-scan', 'reports'] });
    },
    onError: (err: unknown) => {
      message.error(
        `扫描提交失败：${err instanceof Error ? err.message : '未知错误'}`,
      );
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
      message.error(
        `批量提交失败：${err instanceof Error ? err.message : '未知错误'}`,
      );
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
  const candidates: Array<{
    code: string;
    name: string;
    layer: string;
    scarcity_score: number;
    thesis: string;
  }> =
    (selectedReport?.ranked_candidates as any[])?.map((c: any) => ({
      code: c.code ?? c.stock_code ?? '',
      name: c.name ?? '',
      layer: c.layer ?? '',
      scarcity_score: c.scarcity_score ?? 0,
      thesis: c.thesis ?? '',
    })) ?? [];

  return (
    <div
      style={{
        borderLeft: `3px solid ${COLORS.jade.primary}`,
        background: COLORS.jade.light,
        borderRadius: 8,
        padding: 16,
        minHeight: '100%',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginBottom: 16,
        }}
      >
        <BugOutlined style={{ color: COLORS.jade.icon, fontSize: 20 }} />
        <div>
          <Text strong style={{ fontSize: 15, color: COLORS.jade.primary }}>
            产业链卡点引擎
          </Text>
          <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
            theme_scan
          </Text>
        </div>
      </div>

      {/* Trigger New Scan */}
      <div
        style={{
          background: '#fff',
          borderRadius: 8,
          border: '1px solid #E2E8F0',
          padding: 12,
          marginBottom: 12,
        }}
      >
        <Text strong style={{ fontSize: 13, display: 'block', marginBottom: 8 }}>
          发起新扫描
        </Text>
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
            style={{ background: COLORS.jade.primary }}
          >
            扫描
          </Button>
        </Space>
      </div>

      {/* Reports List */}
      <QueryBoundary
        query={reportsQuery}
        isEmpty={(d) => d.length === 0}
      >
        {(reports) => (
          <div
            style={{
              background: '#fff',
              borderRadius: 8,
              border: '1px solid #E2E8F0',
              padding: 12,
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 8,
              }}
            >
              <Text strong style={{ fontSize: 13 }}>
                历史扫描报告
              </Text>
              <Button
                size="small"
                icon={<ReloadOutlined />}
                onClick={() => reportsQuery.refetch()}
              >
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
                    background:
                      selectedReportId === item.id
                        ? COLORS.jade.light
                        : undefined,
                    borderRadius: 6,
                    padding: '8px 10px',
                  }}
                  extra={
                    <Space size={4}>
                      <Tag
                        color={
                          item.status === 'completed' ? 'success' : 'warning'
                        }
                        style={{ fontSize: 11, marginRight: 0 }}
                      >
                        {item.status}
                      </Tag>
                      {item.evidence_grade && (
                        <Tag style={{ fontSize: 11, marginRight: 0 }}>
                          {item.evidence_grade}
                        </Tag>
                      )}
                    </Space>
                  }
                >
                  <List.Item.Meta
                    title={
                      <Space>
                        <FileTextOutlined style={{ color: COLORS.jade.icon }} />
                        <Text strong style={{ fontSize: 13 }}>
                          {item.theme}
                        </Text>
                      </Space>
                    }
                    description={
                      item.created_at ? (
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          {new Date(item.created_at).toLocaleString('zh-CN')}
                        </Text>
                      ) : undefined
                    }
                  />
                </List.Item>
              )}
            />
          </div>
        )}
      </QueryBoundary>

      {/* Selected Report Detail */}
      {selectedReport && candidates.length > 0 && (
        <div
          style={{
            background: '#fff',
            borderRadius: 8,
            border: '1px solid #E2E8F0',
            padding: 12,
            marginTop: 12,
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 8,
            }}
          >
            <Text strong style={{ fontSize: 13 }}>
              候选股票：{selectedReport.theme}
            </Text>
            {candidateCodes.size > 0 && (
              <Button
                size="small"
                type="primary"
                icon={<ThunderboltOutlined />}
                onClick={handleBatchResearch}
                loading={batchResearchM.isPending}
                style={{ background: COLORS.jade.primary }}
              >
                一键深研 ({candidateCodes.size})
              </Button>
            )}
          </div>
          {candidates.map((c) => (
            <div
              key={c.code}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '8px 10px',
                cursor: 'pointer',
                borderRadius: 6,
                background: candidateCodes.has(c.code)
                  ? COLORS.jade.light
                  : undefined,
                borderBottom: '1px solid #F1F5F9',
                transition: 'background 0.15s',
              }}
              onMouseEnter={(e) => {
                if (!candidateCodes.has(c.code))
                  (e.currentTarget as HTMLElement).style.background = '#FAFAFA';
              }}
              onMouseLeave={(e) => {
                if (!candidateCodes.has(c.code))
                  (e.currentTarget as HTMLElement).style.background = '';
              }}
              onClick={() => {
                const next = new Set(candidateCodes);
                if (next.has(c.code)) next.delete(c.code);
                else next.add(c.code);
                setCandidateCodes(next);
              }}
            >
              <Space>
                <a
                  onClick={(e) => {
                    e.stopPropagation();
                    onNavigateToStock(c.code);
                  }}
                  style={{
                    fontFamily: 'var(--font-mono, monospace)',
                    fontSize: 13,
                  }}
                >
                  {c.code}
                </a>
                <Text style={{ fontSize: 13 }}>{c.name}</Text>
                <Tag
                  color="purple"
                  style={{ fontSize: 11, marginRight: 0 }}
                >
                  {c.layer}
                </Tag>
              </Space>
              <Space>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  稀缺分 {c.scarcity_score?.toFixed(1)}
                </Text>
                {candidateCodes.has(c.code) && (
                  <CheckCircleOutlined
                    style={{ color: COLORS.jade.primary, fontSize: 14 }}
                  />
                )}
              </Space>
            </div>
          ))}
        </div>
      )}
    </div>
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
