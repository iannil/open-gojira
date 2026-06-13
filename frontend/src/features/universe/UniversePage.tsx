import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Badge,
  Button,
  Col,
  Collapse,
  InputNumber,
  Row,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Input,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { FilterOutlined, SearchOutlined } from '@ant-design/icons';

import { PageHeader, FilterBar, EmptyState, StatCard } from '../../components/primitives';
import QueryBoundary from '../../components/QueryBoundary';
import { defaultPagination } from '../../lib/pagination';
import {
  useFullUniverseQuery,
  useMyUniverseQuery,
  useUniverseStatsQuery,
} from './useUniverseQueries';
import type { FullUniverseFilter } from './queries';
import type { FullUniverseItem, UniverseItem } from '../../api/types';

const { Text } = Typography;

const TIER_CONFIG: Record<string, { label: string; color: string }> = {
  core: { label: '核心', color: 'gold' },
  watch: { label: '关注', color: 'blue' },
  focus: { label: '重点', color: 'green' },
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

const QIU_SCORE_OPTIONS = [0, 1, 2, 3].map((v) => ({ value: v, label: String(v) }));

const PLAN_STATUS_LABEL: Record<string, string> = {
  active: '运行中',
  paused: '已暂停',
  archived: '已归档',
};

type ViewMode = '我的 Universe' | '全市场';

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
  const [myFilter, setMyFilter] = useState<MyUniverseFilter>(DEFAULT_MY_FILTER);
  const [fullFilter, setFullFilter] = useState<FullMarketFilter>(DEFAULT_FULL_FILTER);
  const [fullPage, setFullPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [filterOpen, setFilterOpen] = useState(false);

  const isFullMarket = viewMode === '全市场';

  const statsQ = useUniverseStatsQuery();
  const myQ = useMyUniverseQuery();
  const fullQueryArgs: FullUniverseFilter = useMemo(
    () => ({
      page: fullPage,
      page_size: pageSize,
      pe_pct_max: fullFilter.pePctMax,
      pb_pct_max: fullFilter.pbPctMax,
      dyr_min: fullFilter.dyrMin ? fullFilter.dyrMin / 100 : undefined,
      pe_ttm_min: fullFilter.peTtmMin,
      pe_ttm_max: fullFilter.peTtmMax,
      pb_min: fullFilter.pbMin,
      pb_max: fullFilter.pbMax,
      industry: fullFilter.industry,
      keyword: fullFilter.keyword.trim() || undefined,
    }),
    [fullPage, pageSize, fullFilter],
  );
  const fullQ = useFullUniverseQuery(fullQueryArgs);

  const data = myQ.data ?? [];
  const fullData = fullQ.data?.items ?? [];
  const fullTotal = fullQ.data?.total ?? 0;

  const myIndustryOptions = useMemo(() => {
    const set = new Set<string>();
    data.forEach((d) => {
      if (d.industry) set.add(d.industry);
    });
    return Array.from(set).sort().map((v) => ({ value: v, label: v }));
  }, [data]);

  const fullIndustryOptions = useMemo(() => {
    const set = new Set<string>();
    fullData.forEach((d) => {
      if (d.industry) set.add(d.industry);
    });
    return Array.from(set).sort().map((v) => ({ value: v, label: v }));
  }, [fullData]);

  const filteredMyData = useMemo(() => {
    const kw = myFilter.keyword.trim().toLowerCase();
    return data.filter((d) => {
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
        if (myFilter.planStatus !== 'none' && (!d.has_plan || d.plan_status !== myFilter.planStatus))
          return false;
      }
      if (myFilter.isHeld) {
        if (myFilter.isHeld === 'yes' && !d.is_held) return false;
        if (myFilter.isHeld === 'no' && d.is_held) return false;
      }
      if (myFilter.pePctMax != null && (d.latest_pe_pct === null || d.latest_pe_pct > myFilter.pePctMax))
        return false;
      if (myFilter.dyrMin != null && (d.latest_dyr === null || d.latest_dyr * 100 < myFilter.dyrMin))
        return false;
      return true;
    });
  }, [data, myFilter]);

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
    setMyFilter((prev) => ({ ...prev, [key]: value }));
  };
  const setFullField = <K extends keyof FullMarketFilter>(key: K, value: FullMarketFilter[K]) => {
    setFullFilter((prev) => ({ ...prev, [key]: value }));
    setFullPage(1);
  };

  const resetMyFilter = () => setMyFilter(DEFAULT_MY_FILTER);
  const resetFullFilter = () => {
    setFullFilter(DEFAULT_FULL_FILTER);
    setFullPage(1);
  };

  // ── Columns ──────────────────────────────────────────────────────────

  const myColumns: ColumnsType<UniverseItem> = [
    {
      title: '代码',
      dataIndex: 'code',
      width: 90,
      render: (code: string) => (
        <a onClick={() => navigate(`/stock/${code}`)}>
          <Text code>{code}</Text>
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
      render: (v: string | null) => v ?? <Text type="secondary">--</Text>,
    },
    { title: '行业', dataIndex: 'industry', width: 90, ellipsis: true },
    {
      title: '求分',
      dataIndex: 'qiu_score',
      width: 55,
      align: 'center',
      render: (v: number) => (
        <span
          className="num"
          style={{
            fontWeight: v >= 2 ? 600 : 400,
            color: v >= 2 ? 'var(--green-600)' : v > 0 ? 'var(--amber-600)' : 'var(--text-tertiary)',
          }}
        >
          {v}
        </span>
      ),
    },
    {
      title: '预案',
      dataIndex: 'has_plan',
      width: 70,
      align: 'center',
      render: (has: boolean, row: UniverseItem) =>
        has ? (
          <Tag color="green">{PLAN_STATUS_LABEL[row.plan_status ?? ''] ?? '候选'}</Tag>
        ) : (
          <Tooltip title="无预案">
            <span style={{ color: 'var(--red-600)' }}>!</span>
          </Tooltip>
        ),
    },
    {
      title: '持有',
      dataIndex: 'is_held',
      width: 70,
      align: 'center',
      render: (v: boolean, row: UniverseItem) =>
        v ? (
          <span className="num">
            {row.weight_pct !== null ? `${row.weight_pct.toFixed(1)}%` : 'Y'}
          </span>
        ) : (
          <Text type="secondary">--</Text>
        ),
    },
    {
      title: 'PE%',
      dataIndex: 'latest_pe_pct',
      width: 60,
      align: 'right',
      render: (v: number | null) =>
        v !== null ? <span className="num">{v.toFixed(1)}</span> : <Text type="secondary">--</Text>,
    },
    {
      title: 'DYR',
      dataIndex: 'latest_dyr',
      width: 70,
      align: 'right',
      render: (v: number | null) =>
        v !== null ? (
          <span className="num">{(v * 100).toFixed(2)}%</span>
        ) : (
          <Text type="secondary">--</Text>
        ),
    },
  ];

  const fullColumns: ColumnsType<FullUniverseItem> = [
    {
      title: '代码',
      dataIndex: 'code',
      width: 90,
      render: (code: string) => (
        <a onClick={() => navigate(`/stock/${code}`)}>
          <Text code>{code}</Text>
        </a>
      ),
    },
    { title: '名称', dataIndex: 'name', width: 100, ellipsis: true },
    {
      title: '行业',
      dataIndex: 'industry',
      width: 100,
      ellipsis: true,
      render: (v: string | null) => v ?? <Text type="secondary">--</Text>,
    },
    {
      title: 'PE%',
      dataIndex: 'latest_pe_pct',
      width: 70,
      align: 'right',
      render: (v: number | null) =>
        v !== null ? <span className="num">{v.toFixed(1)}</span> : <Text type="secondary">--</Text>,
    },
    {
      title: 'PB%',
      dataIndex: 'latest_pb_pct',
      width: 70,
      align: 'right',
      render: (v: number | null) =>
        v !== null ? <span className="num">{v.toFixed(1)}</span> : <Text type="secondary">--</Text>,
    },
    {
      title: 'PE(TTM)',
      dataIndex: 'latest_pe_ttm',
      width: 80,
      align: 'right',
      render: (v: number | null) =>
        v !== null ? <span className="num">{v.toFixed(1)}</span> : <Text type="secondary">--</Text>,
    },
    {
      title: 'PB',
      dataIndex: 'latest_pb',
      width: 70,
      align: 'right',
      render: (v: number | null) =>
        v !== null ? <span className="num">{v.toFixed(2)}</span> : <Text type="secondary">--</Text>,
    },
    {
      title: 'DYR',
      dataIndex: 'latest_dyr',
      width: 80,
      align: 'right',
      render: (v: number | null) =>
        v !== null ? (
          <span className="num">{(v * 100).toFixed(2)}%</span>
        ) : (
          <Text type="secondary">--</Text>
        ),
    },
  ];

  const hasFullCoverage = statsQ.data?.mode === 'full_coverage';
  const segments: string[] = ['我的 Universe'];
  if (hasFullCoverage) segments.push('全市场');

  // Stat cards for My Universe summary
  const mySummary = useMemo(() => {
    const coreCount = filteredMyData.filter((d) => d.tier === 'core').length;
    const watchCount = filteredMyData.filter((d) => d.tier === 'watch').length;
    const noTier = filteredMyData.filter((d) => !d.tier).length;
    const noPlan = filteredMyData.filter((d) => !d.has_plan).length;
    const heldCount = filteredMyData.filter((d) => d.is_held).length;
    return { coreCount, watchCount, noTier, noPlan, heldCount };
  }, [filteredMyData]);

  return (
    <div>
      <PageHeader
        title="股票池"
        enLabel="Universe"
        purpose="你订阅/关注的股票清单 —— 介于全市场和候选池之间的『待观察层』。分层（核心/关注）和主题（能源/粮食/...）由你手工标注，决定哪些股票值得进入预案的扫描范围。"
        flow={[
          { label: '股票池' },
          { to: '/strategies', label: '策略库' },
          { to: '/plans', label: '预案' },
        ]}
      />

      <FilterBar
        onReset={
          (isFullMarket ? fullFilterCount : myFilterCount) > 0
            ? isFullMarket
              ? resetFullFilter
              : resetMyFilter
            : undefined
        }
      >
        <Segmented
          options={segments}
          value={viewMode}
          onChange={(val) => setViewMode(val as ViewMode)}
        />
        <Input.Search
          placeholder="搜索代码/名称"
          allowClear
          style={{ width: 200 }}
          prefix={<SearchOutlined />}
          value={isFullMarket ? fullFilter.keyword : myFilter.keyword}
          onChange={(e) =>
            isFullMarket
              ? setFullField('keyword', e.target.value)
              : setMyField('keyword', e.target.value)
          }
        />
        <Badge count={activeFilterCount} size="small">
          <Button icon={<FilterOutlined />} onClick={() => setFilterOpen(!filterOpen)}>
            筛选
          </Button>
        </Badge>
      </FilterBar>

      <Collapse
        activeKey={filterOpen ? ['filters'] : []}
        onChange={() => setFilterOpen(!filterOpen)}
        ghost
        style={{ marginBottom: 'var(--sp-3)' }}
        items={[
          {
            key: 'filters',
            label: null,
            children: isFullMarket ? (
              <div
                style={{
                  padding: 'var(--sp-3) var(--sp-4)',
                  background: 'var(--surface-raised)',
                  borderRadius: 'var(--radius-lg)',
                  border: '1px solid var(--border-light)',
                }}
              >
                <Row gutter={[12, 12]}>
                  <Col span={6}>
                    <Select
                      placeholder="行业"
                      allowClear
                      showSearch
                      style={{ width: '100%' }}
                      value={fullFilter.industry}
                      onChange={(v) => setFullField('industry', v)}
                      options={fullIndustryOptions}
                    />
                  </Col>
                  <Col span={6}>
                    <Space.Compact style={{ width: '100%' }}>
                      <span
                        style={{
                          lineHeight: '32px',
                          fontSize: 'var(--fs-xs)',
                          color: 'var(--text-tertiary)',
                          whiteSpace: 'nowrap',
                          paddingRight: 4,
                        }}
                      >
                        PE(TTM)
                      </span>
                      <InputNumber
                        style={{ width: '50%' }}
                        size="small"
                        min={0}
                        placeholder="最小"
                        value={fullFilter.peTtmMin ?? undefined}
                        onChange={(v) => setFullField('peTtmMin', v ?? undefined)}
                      />
                      <InputNumber
                        style={{ width: '50%' }}
                        size="small"
                        min={0}
                        placeholder="最大"
                        value={fullFilter.peTtmMax ?? undefined}
                        onChange={(v) => setFullField('peTtmMax', v ?? undefined)}
                      />
                    </Space.Compact>
                  </Col>
                  <Col span={6}>
                    <Space.Compact style={{ width: '100%' }}>
                      <span
                        style={{
                          lineHeight: '32px',
                          fontSize: 'var(--fs-xs)',
                          color: 'var(--text-tertiary)',
                          whiteSpace: 'nowrap',
                          paddingRight: 4,
                        }}
                      >
                        PB
                      </span>
                      <InputNumber
                        style={{ width: '50%' }}
                        size="small"
                        min={0}
                        placeholder="最小"
                        value={fullFilter.pbMin ?? undefined}
                        onChange={(v) => setFullField('pbMin', v ?? undefined)}
                      />
                      <InputNumber
                        style={{ width: '50%' }}
                        size="small"
                        min={0}
                        placeholder="最大"
                        value={fullFilter.pbMax ?? undefined}
                        onChange={(v) => setFullField('pbMax', v ?? undefined)}
                      />
                    </Space.Compact>
                  </Col>
                  <Col span={6}>
                    <Space>
                      <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}>PE% ≤</span>
                      <InputNumber
                        size="small"
                        style={{ width: 80 }}
                        min={0}
                        max={100}
                        value={fullFilter.pePctMax ?? undefined}
                        onChange={(v) => setFullField('pePctMax', v ?? undefined)}
                        placeholder="不限"
                      />
                    </Space>
                  </Col>
                  <Col span={6}>
                    <Space>
                      <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}>PB% ≤</span>
                      <InputNumber
                        size="small"
                        style={{ width: 80 }}
                        min={0}
                        max={100}
                        value={fullFilter.pbPctMax ?? undefined}
                        onChange={(v) => setFullField('pbPctMax', v ?? undefined)}
                        placeholder="不限"
                      />
                    </Space>
                  </Col>
                  <Col span={6}>
                    <Space>
                      <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}>
                        股息率 ≥ %
                      </span>
                      <InputNumber
                        size="small"
                        style={{ width: 80 }}
                        min={0}
                        max={20}
                        step={0.5}
                        value={fullFilter.dyrMin ?? undefined}
                        onChange={(v) => setFullField('dyrMin', v ?? undefined)}
                        placeholder="不限"
                      />
                    </Space>
                  </Col>
                </Row>
                <div style={{ marginTop: 'var(--sp-3)', textAlign: 'right' }}>
                  <Button onClick={resetFullFilter}>重置</Button>
                </div>
              </div>
            ) : (
              <div
                style={{
                  padding: 'var(--sp-3) var(--sp-4)',
                  background: 'var(--surface-raised)',
                  borderRadius: 'var(--radius-lg)',
                  border: '1px solid var(--border-light)',
                }}
              >
                <Row gutter={[12, 12]}>
                  <Col span={6}>
                    <Select
                      placeholder="分层"
                      allowClear
                      style={{ width: '100%' }}
                      value={myFilter.tier}
                      onChange={(v) => setMyField('tier', v)}
                      options={TIER_OPTIONS}
                    />
                  </Col>
                  <Col span={6}>
                    <Select
                      placeholder="安全主题"
                      allowClear
                      style={{ width: '100%' }}
                      value={myFilter.securityTheme}
                      onChange={(v) => setMyField('securityTheme', v)}
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
                      onChange={(v) => setMyField('industry', v)}
                      options={myIndustryOptions}
                    />
                  </Col>
                  <Col span={6}>
                    <Select
                      placeholder="求分"
                      allowClear
                      style={{ width: '100%' }}
                      value={myFilter.qiuScore}
                      onChange={(v) => setMyField('qiuScore', v)}
                      options={QIU_SCORE_OPTIONS}
                    />
                  </Col>
                  <Col span={6}>
                    <Select
                      placeholder="预案状态"
                      allowClear
                      style={{ width: '100%' }}
                      value={myFilter.planStatus}
                      onChange={(v) => setMyField('planStatus', v)}
                      options={PLAN_STATUS_OPTIONS}
                    />
                  </Col>
                  <Col span={6}>
                    <Select
                      placeholder="是否持有"
                      allowClear
                      style={{ width: '100%' }}
                      value={myFilter.isHeld}
                      onChange={(v) => setMyField('isHeld', v)}
                      options={HELD_OPTIONS}
                    />
                  </Col>
                  <Col span={6}>
                    <Space>
                      <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}>PE% ≤</span>
                      <InputNumber
                        size="small"
                        style={{ width: 80 }}
                        min={0}
                        max={100}
                        value={myFilter.pePctMax ?? undefined}
                        onChange={(v) => setMyField('pePctMax', v ?? undefined)}
                        placeholder="不限"
                      />
                    </Space>
                  </Col>
                  <Col span={6}>
                    <Space>
                      <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}>
                        股息率 ≥ %
                      </span>
                      <InputNumber
                        size="small"
                        style={{ width: 80 }}
                        min={0}
                        max={20}
                        step={0.5}
                        value={myFilter.dyrMin ?? undefined}
                        onChange={(v) => setMyField('dyrMin', v ?? undefined)}
                        placeholder="不限"
                      />
                    </Space>
                  </Col>
                </Row>
                <div style={{ marginTop: 'var(--sp-3)', textAlign: 'right' }}>
                  <Button onClick={resetMyFilter}>重置</Button>
                </div>
              </div>
            ),
          },
        ]}
      />

      {isFullMarket ? (
        <>
          <div style={{ marginBottom: 'var(--sp-3)', color: 'var(--text-secondary)' }}>
            共 <span className="num">{fullTotal}</span> 只
          </div>
          <QueryBoundary query={fullQ}>
            {() => (
              <Table<FullUniverseItem>
                dataSource={fullData}
                columns={fullColumns}
                rowKey="code"
                size="small"
                loading={fullQ.isFetching}
                pagination={{
                  ...defaultPagination,
                  current: fullPage,
                  total: fullTotal,
                  defaultPageSize: 50,
                  onChange: (p, ps) => {
                    setFullPage(p);
                    setPageSize(ps);
                  },
                }}
              />
            )}
          </QueryBoundary>
        </>
      ) : (
        <QueryBoundary
          query={myQ}
          isEmpty={(d) => d.length === 0}
          emptyRender={
            <EmptyState
              variant="cold"
              title="股票池为空"
              description="通过「数据管理 → 股票池」添加自选股，或启用全量覆盖模式自动同步所有 A 股。"
            />
          }
        >
          {() => (
            <>
              {filteredMyData.length === 0 ? (
                <EmptyState
                  variant="filter"
                  title="无匹配股票"
                  onClearFilter={resetMyFilter}
                />
              ) : (
                <>
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
                      gap: 'var(--sp-3)',
                      marginBottom: 'var(--sp-4)',
                    }}
                  >
                    <StatCard
                      label="总数"
                      value={filteredMyData.length}
                      hint={myFilterCount > 0 ? `筛选自 ${data.length}` : undefined}
                    />
                    <StatCard label="核心" value={mySummary.coreCount} />
                    <StatCard label="关注" value={mySummary.watchCount} />
                    <StatCard label="已持仓" value={mySummary.heldCount} />
                    {mySummary.noPlan > 0 && (
                      <StatCard
                        label="无预案"
                        value={mySummary.noPlan}
                        hint="考虑加进某个预案的扫描范围"
                      />
                    )}
                  </div>
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
        </QueryBoundary>
      )}
    </div>
  );
}
