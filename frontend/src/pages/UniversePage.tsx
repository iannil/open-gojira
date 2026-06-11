import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Table, Tag, Tooltip, Empty, Spin, Segmented, InputNumber, Space,
  Select, Badge, Button, Collapse, Row, Col, Input,
} from 'antd';
import { FilterOutlined, SearchOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { fetchUniverse, fetchFullUniverse, fetchUniverseStats } from '../api/client';
import PageHeader from '../components/PageHeader';
import type { UniverseItem, FullUniverseItem, UniverseCoverageStats } from '../api/types';

const TIER_CONFIG: Record<string, { label: string; color: string }> = {
  core: { label: '核心', color: '#B8860B' },
  watch: { label: '关注', color: '#6A5ACD' },
  focus: { label: '关注', color: '#6A5ACD' },
};

const TIER_OPTIONS = [
  { value: 'core', label: '核心' },
  { value: 'watch', label: '关注' },
  { value: 'none', label: '未设' },
];

const SECURITY_THEME_OPTIONS = [
  { value: '能源', label: '能源' },
  { value: '粮食', label: '粮食' },
  { value: '金融', label: '金融' },
  { value: '资源', label: '资源' },
  { value: '科技', label: '科技' },
  { value: '信息', label: '信息' },
  { value: '民生', label: '民生' },
];

const PLAN_STATUS_OPTIONS = [
  { value: 'active', label: '运行中' },
  { value: 'paused', label: '已暂停' },
  { value: 'archived', label: '已归档' },
  { value: 'none', label: '无预案' },
];

const HELD_OPTIONS = [
  { value: 'yes', label: '已持有' },
  { value: 'no', label: '未持有' },
];

const QIU_SCORE_OPTIONS = [
  { value: 0, label: '0' },
  { value: 1, label: '1' },
  { value: 2, label: '2' },
  { value: 3, label: '3' },
];

const PLAN_STATUS_LABEL: Record<string, string> = {
  active: '运行中',
  paused: '已暂停',
  archived: '已归档',
};

type ViewMode = '我的 Universe' | '全市场';

// ── Filter state ────────────────────────────────────────────────────────

interface MyUniverseFilter {
  keyword: string;
  tier: string | undefined;
  securityTheme: string | undefined;
  industry: string | undefined;
  qiuScore: number | undefined;
  planStatus: string | undefined;
  isHeld: string | undefined;
  pePctMax: number | undefined;
  dyrMin: number | undefined;
}

const DEFAULT_MY_FILTER: MyUniverseFilter = {
  keyword: '',
  tier: undefined,
  securityTheme: undefined,
  industry: undefined,
  qiuScore: undefined,
  planStatus: undefined,
  isHeld: undefined,
  pePctMax: undefined,
  dyrMin: undefined,
};

interface FullMarketFilter {
  keyword: string;
  industry: string | undefined;
  pePctMax: number | undefined;
  pbPctMax: number | undefined;
  dyrMin: number | undefined;
  peTtmMin: number | undefined;
  peTtmMax: number | undefined;
  pbMin: number | undefined;
  pbMax: number | undefined;
}

const DEFAULT_FULL_FILTER: FullMarketFilter = {
  keyword: '',
  industry: undefined,
  pePctMax: undefined,
  pbPctMax: undefined,
  dyrMin: undefined,
  peTtmMin: undefined,
  peTtmMax: undefined,
  pbMin: undefined,
  pbMax: undefined,
};

export default function UniversePage() {
  const navigate = useNavigate();
  const [viewMode, setViewMode] = useState<ViewMode>('我的 Universe');
  const [data, setData] = useState<UniverseItem[]>([]);
  const [fullData, setFullData] = useState<FullUniverseItem[]>([]);
  const [fullTotal, setFullTotal] = useState(0);
  const [fullPage, setFullPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<UniverseCoverageStats | null>(null);
  const [myFilter, setMyFilter] = useState<MyUniverseFilter>(DEFAULT_MY_FILTER);
  const [fullFilter, setFullFilter] = useState<FullMarketFilter>(DEFAULT_FULL_FILTER);
  const [filterOpen, setFilterOpen] = useState(false);

  const isFullMarket = viewMode === '全市场';

  // Load stats to determine available modes
  useEffect(() => {
    fetchUniverseStats().then(setStats).catch(() => {});
  }, []);

  // Load data based on view mode
  const loadMyUniverse = useCallback(() => {
    setLoading(true);
    fetchUniverse()
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const loadFullMarket = useCallback((page: number, f: FullMarketFilter) => {
    setLoading(true);
    fetchFullUniverse({
      page,
      page_size: 50,
      pe_pct_max: f.pePctMax ?? undefined,
      pb_pct_max: f.pbPctMax ?? undefined,
      dyr_min: f.dyrMin ? f.dyrMin / 100 : undefined,
      pe_ttm_min: f.peTtmMin ?? undefined,
      pe_ttm_max: f.peTtmMax ?? undefined,
      pb_min: f.pbMin ?? undefined,
      pb_max: f.pbMax ?? undefined,
      industry: f.industry ?? undefined,
      keyword: f.keyword.trim() || undefined,
    })
      .then((res) => {
        setFullData(res.items);
        setFullTotal(res.total);
        setFullPage(res.page);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (isFullMarket) {
      loadFullMarket(1, fullFilter);
    } else {
      loadMyUniverse();
    }
  }, [isFullMarket, loadMyUniverse, loadFullMarket, fullFilter]);

  const handleViewChange = useCallback((val: string) => {
    setViewMode(val as ViewMode);
  }, []);

  // ── Dynamic options from data ────────────────────────────────────────

  const myIndustryOptions = useMemo(() => {
    const set = new Set<string>();
    data.forEach(d => { if (d.industry) set.add(d.industry); });
    return Array.from(set).sort().map(v => ({ value: v, label: v }));
  }, [data]);

  const fullIndustryOptions = useMemo(() => {
    const set = new Set<string>();
    fullData.forEach(d => { if (d.industry) set.add(d.industry); });
    return Array.from(set).sort().map(v => ({ value: v, label: v }));
  }, [fullData]);

  // ── Client-side filtering for My Universe ────────────────────────────

  const filteredMyData = useMemo(() => {
    const kw = myFilter.keyword.trim().toLowerCase();
    return data.filter(d => {
      if (kw) {
        const haystack = `${d.code} ${d.name}`.toLowerCase();
        if (!haystack.includes(kw)) return false;
      }
      if (myFilter.tier) {
        if (myFilter.tier === 'none' && d.tier) return false;
        if (myFilter.tier !== 'none' && d.tier !== myFilter.tier) return false;
      }
      if (myFilter.securityTheme && d.security_theme !== myFilter.securityTheme) return false;
      if (myFilter.industry && d.industry !== myFilter.industry) return false;
      if (myFilter.qiuScore !== undefined && d.qiu_score !== myFilter.qiuScore) return false;
      if (myFilter.planStatus) {
        if (myFilter.planStatus === 'none' && d.has_plan) return false;
        if (myFilter.planStatus !== 'none' && (!d.has_plan || d.plan_status !== myFilter.planStatus)) return false;
      }
      if (myFilter.isHeld) {
        if (myFilter.isHeld === 'yes' && !d.is_held) return false;
        if (myFilter.isHeld === 'no' && d.is_held) return false;
      }
      if (myFilter.pePctMax != null && (d.latest_pe_pct === null || d.latest_pe_pct > myFilter.pePctMax)) return false;
      if (myFilter.dyrMin != null && (d.latest_dyr === null || d.latest_dyr * 100 < myFilter.dyrMin)) return false;
      return true;
    });
  }, [data, myFilter]);

  const filteredFullData = fullData;

  // ── Active filter count ──────────────────────────────────────────────

  const myFilterCount = useMemo(() => {
    let c = 0;
    if (myFilter.keyword) c++;
    if (myFilter.tier) c++;
    if (myFilter.securityTheme) c++;
    if (myFilter.industry) c++;
    if (myFilter.qiuScore !== undefined) c++;
    if (myFilter.planStatus) c++;
    if (myFilter.isHeld) c++;
    if (myFilter.pePctMax != null) c++;
    if (myFilter.dyrMin != null) c++;
    return c;
  }, [myFilter]);

  const fullFilterCount = useMemo(() => {
    let c = 0;
    if (fullFilter.keyword) c++;
    if (fullFilter.industry) c++;
    if (fullFilter.pePctMax != null) c++;
    if (fullFilter.pbPctMax != null) c++;
    if (fullFilter.dyrMin != null) c++;
    if (fullFilter.peTtmMin != null) c++;
    if (fullFilter.peTtmMax != null) c++;
    if (fullFilter.pbMin != null) c++;
    if (fullFilter.pbMax != null) c++;
    return c;
  }, [fullFilter]);

  const activeFilterCount = isFullMarket ? fullFilterCount : myFilterCount;

  const setMyField = <K extends keyof MyUniverseFilter>(key: K, value: MyUniverseFilter[K]) => {
    setMyFilter(prev => ({ ...prev, [key]: value }));
  };

  const setFullField = <K extends keyof FullMarketFilter>(key: K, value: FullMarketFilter[K]) => {
    setFullFilter(prev => ({ ...prev, [key]: value }));
  };

  // ── Columns ──────────────────────────────────────────────────────────

  const myColumns: ColumnsType<UniverseItem> = [
    {
      title: '代码',
      dataIndex: 'code',
      width: 90,
      render: (code: string) => (
        <a onClick={() => navigate(`/stock/${code}`)} style={{ fontFamily: 'monospace' }}>
          {code}
        </a>
      ),
    },
    { title: '名称', dataIndex: 'name', width: 100, ellipsis: true },
    {
      title: '分层',
      dataIndex: 'tier',
      width: 70,
      render: (tier: string | null) => {
        if (!tier) return <Tag color="default">未设</Tag>;
        const cfg = TIER_CONFIG[tier];
        return cfg ? <Tag color={cfg.color}>{cfg.label}</Tag> : <Tag>{tier}</Tag>;
      },
    },
    {
      title: '主题',
      dataIndex: 'security_theme',
      width: 80,
      ellipsis: true,
      render: (v: string | null) => v || <span style={{ color: '#A8A29E' }}>--</span>,
    },
    {
      title: '行业',
      dataIndex: 'industry',
      width: 90,
      ellipsis: true,
    },
    {
      title: '求分',
      dataIndex: 'qiu_score',
      width: 55,
      align: 'center',
      render: (v: number) => (
        <span style={{ fontWeight: v >= 2 ? 600 : 400, color: v >= 2 ? '#16A34A' : v > 0 ? '#D97706' : '#A8A29E' }}>
          {v}
        </span>
      ),
    },
    {
      title: '预案',
      dataIndex: 'has_plan',
      width: 60,
      align: 'center',
      render: (has: boolean, row: UniverseItem) =>
        has ? (
          <Tag color="green">{PLAN_STATUS_LABEL[row.plan_status ?? ''] ?? '候选'}</Tag>
        ) : (
          <Tooltip title="无预案">
            <span style={{ color: '#DC2626' }}>!</span>
          </Tooltip>
        ),
    },
    {
      title: '持有',
      dataIndex: 'is_held',
      width: 55,
      align: 'center',
      render: (v: boolean, row: UniverseItem) =>
        v ? (
          <span>{row.weight_pct !== null ? `${row.weight_pct.toFixed(1)}%` : 'Y'}</span>
        ) : (
          <span style={{ color: '#A8A29E' }}>--</span>
        ),
    },
    {
      title: 'PE%',
      dataIndex: 'latest_pe_pct',
      width: 60,
      align: 'right',
      render: (v: number | null) =>
        v !== null ? `${v.toFixed(1)}` : '--',
    },
    {
      title: 'DYR',
      dataIndex: 'latest_dyr',
      width: 60,
      align: 'right',
      render: (v: number | null) =>
        v !== null ? `${(v * 100).toFixed(2)}%` : '--',
    },
  ];

  const fullColumns: ColumnsType<FullUniverseItem> = [
    {
      title: '代码',
      dataIndex: 'code',
      width: 90,
      render: (code: string) => (
        <a onClick={() => navigate(`/stock/${code}`)} style={{ fontFamily: 'monospace' }}>
          {code}
        </a>
      ),
    },
    { title: '名称', dataIndex: 'name', width: 100, ellipsis: true },
    {
      title: '行业',
      dataIndex: 'industry',
      width: 100,
      ellipsis: true,
      render: (v: string | null) => v || '--',
    },
    {
      title: 'PE%',
      dataIndex: 'latest_pe_pct',
      width: 70,
      align: 'right',
      render: (v: number | null) =>
        v !== null ? `${v.toFixed(1)}` : '--',
    },
    {
      title: 'PB%',
      dataIndex: 'latest_pb_pct',
      width: 70,
      align: 'right',
      render: (v: number | null) =>
        v !== null ? `${v.toFixed(1)}` : '--',
    },
    {
      title: 'PE(TTM)',
      dataIndex: 'latest_pe_ttm',
      width: 80,
      align: 'right',
      render: (v: number | null) =>
        v !== null ? `${v.toFixed(1)}` : '--',
    },
    {
      title: 'PB',
      dataIndex: 'latest_pb',
      width: 70,
      align: 'right',
      render: (v: number | null) =>
        v !== null ? `${v.toFixed(2)}` : '--',
    },
    {
      title: 'DYR',
      dataIndex: 'latest_dyr',
      width: 80,
      align: 'right',
      render: (v: number | null) =>
        v !== null ? `${(v * 100).toFixed(2)}%` : '--',
    },
  ];

  if (loading && data.length === 0 && fullData.length === 0) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  const hasFullCoverage = stats?.mode === 'full_coverage';
  const segments: string[] = ['我的 Universe'];
  if (hasFullCoverage) {
    segments.push('全市场');
  }

  return (
    <div>
      <PageHeader title="股票池" enLabel="Universe" />

      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <Segmented
            options={segments}
            value={viewMode}
            onChange={handleViewChange}
          />
          <Input.Search
            placeholder="搜索代码/名称"
            allowClear
            style={{ width: 180 }}
            prefix={<SearchOutlined />}
            value={isFullMarket ? fullFilter.keyword : myFilter.keyword}
            onChange={e => isFullMarket ? setFullField('keyword', e.target.value) : setMyField('keyword', e.target.value)}
          />
          <Badge count={activeFilterCount} size="small">
            <Button
              icon={<FilterOutlined />}
              onClick={() => setFilterOpen(!filterOpen)}
            >
              筛选
            </Button>
          </Badge>
        </Space>
      </div>

      <Collapse
        activeKey={filterOpen ? ['filters'] : []}
        onChange={() => setFilterOpen(!filterOpen)}
        ghost
        items={[{
          key: 'filters',
          label: null,
          children: isFullMarket ? (
            <div style={{ marginBottom: 16, padding: '12px 16px', background: 'var(--bg-secondary, #fafafa)', borderRadius: 8 }}>
              <Row gutter={[12, 12]}>
                <Col span={6}>
                  <Select
                    placeholder="行业"
                    allowClear
                    showSearch
                    style={{ width: '100%' }}
                    value={fullFilter.industry}
                    onChange={v => setFullField('industry', v)}
                    options={fullIndustryOptions}
                  />
                </Col>
                <Col span={6}>
                  <Space.Compact style={{ width: '100%' }}>
                    <span style={{ lineHeight: '32px', fontSize: 12, color: '#78716C', whiteSpace: 'nowrap', paddingRight: 4 }}>PE(TTM)</span>
                    <InputNumber
                      style={{ width: '50%' }}
                      size="small"
                      min={0}
                      placeholder="最小"
                      value={fullFilter.peTtmMin ?? undefined}
                      onChange={v => setFullField('peTtmMin', v ?? undefined)}
                    />
                    <InputNumber
                      style={{ width: '50%' }}
                      size="small"
                      min={0}
                      placeholder="最大"
                      value={fullFilter.peTtmMax ?? undefined}
                      onChange={v => setFullField('peTtmMax', v ?? undefined)}
                    />
                  </Space.Compact>
                </Col>
                <Col span={6}>
                  <Space.Compact style={{ width: '100%' }}>
                    <span style={{ lineHeight: '32px', fontSize: 12, color: '#78716C', whiteSpace: 'nowrap', paddingRight: 4 }}>PB</span>
                    <InputNumber
                      style={{ width: '50%' }}
                      size="small"
                      min={0}
                      placeholder="最小"
                      value={fullFilter.pbMin ?? undefined}
                      onChange={v => setFullField('pbMin', v ?? undefined)}
                    />
                    <InputNumber
                      style={{ width: '50%' }}
                      size="small"
                      min={0}
                      placeholder="最大"
                      value={fullFilter.pbMax ?? undefined}
                      onChange={v => setFullField('pbMax', v ?? undefined)}
                    />
                  </Space.Compact>
                </Col>
                <Col span={6}>
                  <Space>
                    <span style={{ fontSize: 12, color: '#78716C' }}>PE% ≤</span>
                    <InputNumber
                      size="small"
                      style={{ width: 80 }}
                      min={0}
                      max={100}
                      value={fullFilter.pePctMax ?? undefined}
                      onChange={v => setFullField('pePctMax', v ?? undefined)}
                      placeholder="不限"
                    />
                  </Space>
                </Col>
                <Col span={6}>
                  <Space>
                    <span style={{ fontSize: 12, color: '#78716C' }}>PB% ≤</span>
                    <InputNumber
                      size="small"
                      style={{ width: 80 }}
                      min={0}
                      max={100}
                      value={fullFilter.pbPctMax ?? undefined}
                      onChange={v => setFullField('pbPctMax', v ?? undefined)}
                      placeholder="不限"
                    />
                  </Space>
                </Col>
                <Col span={6}>
                  <Space>
                    <span style={{ fontSize: 12, color: '#78716C' }}>股息率 ≥ %</span>
                    <InputNumber
                      size="small"
                      style={{ width: 80 }}
                      min={0}
                      max={20}
                      step={0.5}
                      value={fullFilter.dyrMin ?? undefined}
                      onChange={v => setFullField('dyrMin', v ?? undefined)}
                      placeholder="不限"
                    />
                  </Space>
                </Col>
              </Row>
              <div style={{ marginTop: 12, textAlign: 'right' }}>
                <Button onClick={() => setFullFilter(DEFAULT_FULL_FILTER)}>重置</Button>
              </div>
            </div>
          ) : (
            <div style={{ marginBottom: 16, padding: '12px 16px', background: 'var(--bg-secondary, #fafafa)', borderRadius: 8 }}>
              <Row gutter={[12, 12]}>
                <Col span={6}>
                  <Select
                    placeholder="分层"
                    allowClear
                    style={{ width: '100%' }}
                    value={myFilter.tier}
                    onChange={v => setMyField('tier', v)}
                    options={TIER_OPTIONS}
                  />
                </Col>
                <Col span={6}>
                  <Select
                    placeholder="安全主题"
                    allowClear
                    style={{ width: '100%' }}
                    value={myFilter.securityTheme}
                    onChange={v => setMyField('securityTheme', v)}
                    options={SECURITY_THEME_OPTIONS}
                  />
                </Col>
                <Col span={6}>
                  <Select
                    placeholder="行业"
                    allowClear
                    showSearch
                    style={{ width: '100%' }}
                    value={myFilter.industry}
                    onChange={v => setMyField('industry', v)}
                    options={myIndustryOptions}
                  />
                </Col>
                <Col span={6}>
                  <Select
                    placeholder="求分"
                    allowClear
                    style={{ width: '100%' }}
                    value={myFilter.qiuScore}
                    onChange={v => setMyField('qiuScore', v)}
                    options={QIU_SCORE_OPTIONS}
                  />
                </Col>
                <Col span={6}>
                  <Select
                    placeholder="预案状态"
                    allowClear
                    style={{ width: '100%' }}
                    value={myFilter.planStatus}
                    onChange={v => setMyField('planStatus', v)}
                    options={PLAN_STATUS_OPTIONS}
                  />
                </Col>
                <Col span={6}>
                  <Select
                    placeholder="是否持有"
                    allowClear
                    style={{ width: '100%' }}
                    value={myFilter.isHeld}
                    onChange={v => setMyField('isHeld', v)}
                    options={HELD_OPTIONS}
                  />
                </Col>
                <Col span={6}>
                  <Space>
                    <span style={{ fontSize: 12, color: '#78716C' }}>PE% ≤</span>
                    <InputNumber
                      size="small"
                      style={{ width: 80 }}
                      min={0}
                      max={100}
                      value={myFilter.pePctMax ?? undefined}
                      onChange={v => setMyField('pePctMax', v ?? undefined)}
                      placeholder="不限"
                    />
                  </Space>
                </Col>
                <Col span={6}>
                  <Space>
                    <span style={{ fontSize: 12, color: '#78716C' }}>股息率 ≥ %</span>
                    <InputNumber
                      size="small"
                      style={{ width: 80 }}
                      min={0}
                      max={20}
                      step={0.5}
                      value={myFilter.dyrMin ?? undefined}
                      onChange={v => setMyField('dyrMin', v ?? undefined)}
                      placeholder="不限"
                    />
                  </Space>
                </Col>
              </Row>
              <div style={{ marginTop: 12, textAlign: 'right' }}>
                <Button onClick={() => setMyFilter(DEFAULT_MY_FILTER)}>重置</Button>
              </div>
            </div>
          ),
        }]}
      />

      {isFullMarket ? (
        <>
          <div style={{ marginBottom: 12, fontSize: 13, color: '#57534E' }}>
            共 {fullTotal} 只{filteredFullData.length !== fullData.length && `（当前页筛选 ${filteredFullData.length}）`}
          </div>
          <Table<FullUniverseItem>
            dataSource={filteredFullData}
            columns={fullColumns}
            rowKey="code"
            size="small"
            pagination={{
              current: fullPage,
              total: fullTotal,
              pageSize: 50,
              showSizeChanger: false,
              onChange: (p) => loadFullMarket(p, fullFilter),
            }}
          />
        </>
      ) : (
        <>
          {filteredMyData.length === 0 && data.length === 0 ? (
            <Empty description="股票池为空 — 添加自选股或持仓后可见" />
          ) : (
            <>
              {(() => {
                const coreCount = filteredMyData.filter((d) => d.tier === 'core').length;
                const watchCount = filteredMyData.filter((d) => d.tier === 'watch').length;
                const noTier = filteredMyData.filter((d) => !d.tier).length;
                const noPlan = filteredMyData.filter((d) => !d.has_plan).length;
                return (
                  <div style={{ marginBottom: 12, display: 'flex', gap: 16, fontSize: 13, color: '#57534E' }}>
                    <span>共 {filteredMyData.length} 只{myFilterCount > 0 && `（筛选自 ${data.length}）`}</span>
                    <span>核心 <b style={{ color: '#B8860B' }}>{coreCount}</b></span>
                    <span>关注 <b style={{ color: '#6A5ACD' }}>{watchCount}</b></span>
                    <span>未分级 {noTier}</span>
                    {noPlan > 0 && <span style={{ color: '#DC2626' }}>无预案 {noPlan}</span>}
                  </div>
                );
              })()}
              <Table<UniverseItem>
                dataSource={filteredMyData}
                columns={myColumns}
                rowKey="code"
                size="small"
                pagination={false}
                rowClassName={(record) => (record.is_held ? 'row-held' : '')}
              />
            </>
          )}
        </>
      )}
    </div>
  );
}
