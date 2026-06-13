import { useMemo, useState } from 'react';
import {
  Table,
  Tag,
  Button,
  Select,
  Tooltip,
  Popconfirm,
  Collapse,
  Row,
  Col,
  Switch,
  Badge,
  Input,
} from 'antd';
import {
  FilterOutlined,
  PushpinFilled,
  PushpinOutlined,
  SearchOutlined,
} from '@ant-design/icons';

import { PageHeader, FilterBar, EmptyState } from '../../components/primitives';
import QueryBoundary from '../../components/QueryBoundary';
import { useCandidatesQuery } from './useCandidateQueries';
import {
  useRemoveCandidateMutation,
  useTogglePinCandidateMutation,
} from './useCandidateMutations';
import { usePlansQuery } from '../plans/usePlanQueries';
import type { CandidateResponse } from '../../api/types';

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  active: { color: 'green', label: '活跃' },
  removed: { color: 'red', label: '已移出' },
};

const QUADRANT_OPTIONS = [
  { value: 'procyclical', label: '顺周期' },
  { value: 'countercyclical', label: '逆周期' },
  { value: 'distressed_reversal', label: '困境反转' },
  { value: 'financial', label: '金融' },
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

const TIER_OPTIONS = [
  { value: 'core', label: '核心' },
  { value: 'watch', label: '关注' },
];

const QIU_SCORE_OPTIONS = [0, 1, 2, 3].map((v) => ({ value: v, label: String(v) }));

interface FilterState {
  planId: number | undefined;
  status: string | undefined;
  industry: string | undefined;
  securityTheme: string | undefined;
  quadrant: string | undefined;
  tier: string | undefined;
  qiuScore: number | undefined;
  hqRegion: string | undefined;
  pinned: boolean | undefined;
}

const DEFAULT_FILTER: FilterState = {
  planId: undefined,
  status: 'active',
  industry: undefined,
  securityTheme: undefined,
  quadrant: undefined,
  tier: undefined,
  qiuScore: undefined,
  hqRegion: undefined,
  pinned: undefined,
};

export default function CandidatesPage() {
  const candidatesQ = useCandidatesQuery();
  const plansQ = usePlansQuery();
  const pinM = useTogglePinCandidateMutation();
  const removeM = useRemoveCandidateMutation();

  const [filter, setFilter] = useState<FilterState>(DEFAULT_FILTER);
  const [filterOpen, setFilterOpen] = useState(false);
  const [keyword, setKeyword] = useState('');

  const candidates = candidatesQ.data ?? [];
  const plans = plansQ.data ?? [];

  const industryOptions = useMemo(() => {
    const set = new Set<string>();
    candidates.forEach((c) => {
      if (c.stock_industry) set.add(c.stock_industry);
    });
    return Array.from(set).sort().map((v) => ({ value: v, label: v }));
  }, [candidates]);

  const hqRegionOptions = useMemo(() => {
    const set = new Set<string>();
    candidates.forEach((c) => {
      if (c.stock_hq_region) set.add(c.stock_hq_region);
    });
    return Array.from(set).sort().map((v) => ({ value: v, label: v }));
  }, [candidates]);

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    return candidates.filter((c) => {
      if (kw) {
        const haystack = `${c.stock_code} ${c.stock_name} ${c.plan_name}`.toLowerCase();
        if (!haystack.includes(kw)) return false;
      }
      if (filter.planId !== undefined && c.plan_id !== filter.planId) return false;
      if (filter.status && c.status !== filter.status) return false;
      if (filter.industry && c.stock_industry !== filter.industry) return false;
      if (filter.securityTheme && c.stock_security_theme !== filter.securityTheme)
        return false;
      if (filter.quadrant && c.stock_quadrant !== filter.quadrant) return false;
      if (filter.tier && c.stock_tier !== filter.tier) return false;
      if (filter.qiuScore !== undefined && c.stock_qiu_score !== filter.qiuScore)
        return false;
      if (filter.hqRegion && c.stock_hq_region !== filter.hqRegion) return false;
      if (filter.pinned !== undefined && c.pinned !== filter.pinned) return false;
      return true;
    });
  }, [candidates, filter, keyword]);

  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (filter.planId !== undefined) count++;
    if (filter.status && filter.status !== 'active') count++;
    if (filter.industry) count++;
    if (filter.securityTheme) count++;
    if (filter.quadrant) count++;
    if (filter.tier) count++;
    if (filter.qiuScore !== undefined) count++;
    if (filter.hqRegion) count++;
    if (filter.pinned !== undefined) count++;
    return count;
  }, [filter]);

  const isFiltering =
    activeFilterCount > 0 || keyword.trim().length > 0;

  const setFilterField = <K extends keyof FilterState>(key: K, value: FilterState[K]) => {
    setFilter((prev) => ({ ...prev, [key]: value }));
  };

  const resetFilter = () => {
    setFilter(DEFAULT_FILTER);
    setKeyword('');
  };

  const columns = [
    { title: '代码', dataIndex: 'stock_code', width: 90 },
    { title: '名称', dataIndex: 'stock_name', width: 100 },
    {
      title: '行业',
      dataIndex: 'stock_industry',
      width: 100,
      render: (v: string | null) => v || '-',
    },
    { title: '来源预案', dataIndex: 'plan_name', width: 120 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 80,
      render: (s: string) => (
        <Tag color={STATUS_MAP[s]?.color}>{STATUS_MAP[s]?.label || s}</Tag>
      ),
    },
    {
      title: '首次入池',
      dataIndex: 'first_seen_at',
      width: 120,
      render: (v: string | null) =>
        v ? <span className="num">{v.slice(0, 10)}</span> : '-',
    },
    {
      title: '最近确认',
      dataIndex: 'last_confirmed_at',
      width: 120,
      render: (v: string | null) =>
        v ? <span className="num">{v.slice(0, 10)}</span> : '-',
    },
    {
      title: '固定',
      dataIndex: 'pinned',
      width: 60,
      render: (v: boolean, r: CandidateResponse) =>
        r.status === 'active' ? (
          <Tooltip title={v ? '取消固定' : '固定'}>
            <Button
              type="text"
              size="small"
              icon={
                v ? (
                  <PushpinFilled style={{ color: 'var(--amber-500)' }} />
                ) : (
                  <PushpinOutlined />
                )
              }
              onClick={() => pinM.mutate({ id: r.id, pinned: !r.pinned })}
            />
          </Tooltip>
        ) : null,
    },
    {
      title: '操作',
      width: 100,
      render: (_: unknown, r: CandidateResponse) =>
        r.status === 'active' ? (
          <Popconfirm title="确定移出？" onConfirm={() => removeM.mutate(r.id)}>
            <Button size="small" danger loading={removeM.isPending}>
              移出
            </Button>
          </Popconfirm>
        ) : null,
    },
  ];

  return (
    <div>
      <PageHeader
        title="候选池"
        enLabel="Candidates"
        purpose="预案运行后产出的「值得买」候选股清单。可固定、移出、或转入持仓。所有改动会影响主看板的下一步推荐。"
        flow={[
          { to: '/strategies', label: '策略库' },
          { to: '/plans', label: '预案' },
          { label: '候选池' },
          { to: '/trades', label: '成交流水' },
        ]}
      />

      <FilterBar onReset={isFiltering ? resetFilter : undefined}>
        <Input.Search
          placeholder="搜索代码/名称/预案"
          allowClear
          style={{ width: 220 }}
          prefix={<SearchOutlined />}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
        />
        <Badge count={activeFilterCount} size="small">
          <Button icon={<FilterOutlined />} onClick={() => setFilterOpen(!filterOpen)}>
            筛选
          </Button>
        </Badge>
        <Select
          style={{ width: 120 }}
          value={filter.status}
          onChange={(v) => setFilterField('status', v)}
          options={[
            { value: 'active', label: '活跃' },
            { value: 'removed', label: '已移出' },
            { value: '', label: '全部' },
          ]}
        />
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
            children: (
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
                      placeholder="所属计划"
                      allowClear
                      style={{ width: '100%' }}
                      value={filter.planId}
                      onChange={(v) => setFilterField('planId', v)}
                      options={plans.map((p) => ({ value: p.id, label: p.name }))}
                    />
                  </Col>
                  <Col span={6}>
                    <Select
                      placeholder="行业"
                      allowClear
                      showSearch
                      style={{ width: '100%' }}
                      value={filter.industry}
                      onChange={(v) => setFilterField('industry', v)}
                      options={industryOptions}
                    />
                  </Col>
                  <Col span={6}>
                    <Select
                      placeholder="安全主题"
                      allowClear
                      style={{ width: '100%' }}
                      value={filter.securityTheme}
                      onChange={(v) => setFilterField('securityTheme', v)}
                      options={SECURITY_THEME_OPTIONS}
                    />
                  </Col>
                  <Col span={6}>
                    <Select
                      placeholder="象限"
                      allowClear
                      style={{ width: '100%' }}
                      value={filter.quadrant}
                      onChange={(v) => setFilterField('quadrant', v)}
                      options={QUADRANT_OPTIONS}
                    />
                  </Col>
                  <Col span={6}>
                    <Select
                      placeholder="评级"
                      allowClear
                      style={{ width: '100%' }}
                      value={filter.tier}
                      onChange={(v) => setFilterField('tier', v)}
                      options={TIER_OPTIONS}
                    />
                  </Col>
                  <Col span={6}>
                    <Select
                      placeholder="Qiu评分"
                      allowClear
                      style={{ width: '100%' }}
                      value={filter.qiuScore}
                      onChange={(v) => setFilterField('qiuScore', v)}
                      options={QIU_SCORE_OPTIONS}
                    />
                  </Col>
                  <Col span={6}>
                    <Select
                      placeholder="总部地区"
                      allowClear
                      showSearch
                      style={{ width: '100%' }}
                      value={filter.hqRegion}
                      onChange={(v) => setFilterField('hqRegion', v)}
                      options={hqRegionOptions}
                    />
                  </Col>
                  <Col span={6}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-xs)' }}>
                        仅置顶
                      </span>
                      <Switch
                        checked={filter.pinned === true}
                        onChange={(v) => setFilterField('pinned', v ? true : undefined)}
                      />
                    </span>
                  </Col>
                </Row>
                <div style={{ marginTop: 'var(--sp-3)', textAlign: 'right' }}>
                  <Button onClick={resetFilter}>重置</Button>
                </div>
              </div>
            ),
          },
        ]}
      />

      <QueryBoundary
        query={candidatesQ}
        isEmpty={() => false}
      >
        {() => (
          <>
            {filtered.length === 0 ? (
              <EmptyState
                variant={isFiltering ? 'filter' : 'cold'}
                title={
                  isFiltering
                    ? '无匹配候选'
                    : candidates.length === 0
                      ? '还没有候选股'
                      : '暂无候选'
                }
                description={
                  isFiltering
                    ? '当前筛选条件下无结果'
                    : '预案运行后会自动产出候选股。先去预案页运行一个预案。'
                }
                onClearFilter={isFiltering ? resetFilter : undefined}
                cta={
                  !isFiltering && candidates.length === 0
                    ? { label: '去运行预案', onClick: () => (window.location.href = '/plans') }
                    : undefined
                }
              />
            ) : (
              <Table
                dataSource={filtered}
                columns={columns}
                rowKey="id"
                loading={candidatesQ.isFetching && !candidatesQ.data}
                size="small"
                pagination={{ pageSize: 20, showSizeChanger: false }}
              />
            )}
          </>
        )}
      </QueryBoundary>
    </div>
  );
}
