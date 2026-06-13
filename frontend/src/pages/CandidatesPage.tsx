import { useEffect, useState, useMemo } from 'react';
import {
  Table, Tag, Button, Space, Select, Tooltip, Popconfirm,
  Collapse, Row, Col, Switch, Badge, Input,
} from 'antd';
import { PushpinOutlined, PushpinFilled, FilterOutlined, SearchOutlined } from '@ant-design/icons';
import { useAntdStatic } from '../hooks/useAntdStatic';
import PageHeader from '../components/PageHeader';
import { listCandidates, updateCandidate, removeCandidate, listPlans } from '../api/client';
import type { CandidateResponse, PlanResponse } from '../api/types';

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

const QIU_SCORE_OPTIONS = [
  { value: 0, label: '0' },
  { value: 1, label: '1' },
  { value: 2, label: '2' },
  { value: 3, label: '3' },
];

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
  const { message } = useAntdStatic();
  const [candidates, setCandidates] = useState<CandidateResponse[]>([]);
  const [plans, setPlans] = useState<PlanResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<FilterState>(DEFAULT_FILTER);
  const [filterOpen, setFilterOpen] = useState(false);
  const [keyword, setKeyword] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const [cs, ps] = await Promise.all([
        listCandidates({}),
        listPlans(),
      ]);
      setCandidates(cs);
      setPlans(ps);
    } catch { message.error('加载失败'); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const industryOptions = useMemo(() => {
    const set = new Set<string>();
    candidates.forEach(c => { if (c.stock_industry) set.add(c.stock_industry); });
    return Array.from(set).sort().map(v => ({ value: v, label: v }));
  }, [candidates]);

  const hqRegionOptions = useMemo(() => {
    const set = new Set<string>();
    candidates.forEach(c => { if (c.stock_hq_region) set.add(c.stock_hq_region); });
    return Array.from(set).sort().map(v => ({ value: v, label: v }));
  }, [candidates]);

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    return candidates.filter(c => {
      if (kw) {
        const haystack = `${c.stock_code} ${c.stock_name} ${c.plan_name}`.toLowerCase();
        if (!haystack.includes(kw)) return false;
      }
      if (filter.planId !== undefined && c.plan_id !== filter.planId) return false;
      if (filter.status && c.status !== filter.status) return false;
      if (filter.industry && c.stock_industry !== filter.industry) return false;
      if (filter.securityTheme && c.stock_security_theme !== filter.securityTheme) return false;
      if (filter.quadrant && c.stock_quadrant !== filter.quadrant) return false;
      if (filter.tier && c.stock_tier !== filter.tier) return false;
      if (filter.qiuScore !== undefined && c.stock_qiu_score !== filter.qiuScore) return false;
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

  const setFilterField = <K extends keyof FilterState>(key: K, value: FilterState[K]) => {
    setFilter(prev => ({ ...prev, [key]: value }));
  };

  const resetFilter = () => setFilter(DEFAULT_FILTER);

  const handlePin = async (c: CandidateResponse) => {
    await updateCandidate(c.id, { pinned: !c.pinned });
    message.success(c.pinned ? '已取消固定' : '已固定');
    load();
  };

  const handleRemove = async (id: number) => {
    await removeCandidate(id);
    message.success('已移出');
    load();
  };

  const columns = [
    { title: '代码', dataIndex: 'stock_code', width: 90 },
    { title: '名称', dataIndex: 'stock_name', width: 100 },
    { title: '行业', dataIndex: 'stock_industry', width: 100, render: (v: string | null) => v || '-' },
    { title: '来源预案', dataIndex: 'plan_name', width: 120 },
    {
      title: '状态', dataIndex: 'status', width: 80,
      render: (s: string) => <Tag color={STATUS_MAP[s]?.color}>{STATUS_MAP[s]?.label || s}</Tag>,
    },
    {
      title: '首次入池', dataIndex: 'first_seen_at', width: 120,
      render: (v: string | null) => v ? v.slice(0, 10) : '-',
    },
    {
      title: '最近确认', dataIndex: 'last_confirmed_at', width: 120,
      render: (v: string | null) => v ? v.slice(0, 10) : '-',
    },
    {
      title: '固定', dataIndex: 'pinned', width: 60,
      render: (v: boolean, r: CandidateResponse) =>
        r.status === 'active' ? (
          <Tooltip title={v ? '取消固定' : '固定'}>
            <Button type="text" size="small"
              icon={v ? <PushpinFilled style={{ color: '#faad14' }} /> : <PushpinOutlined />}
              onClick={() => handlePin(r)} />
          </Tooltip>
        ) : null,
    },
    {
      title: '操作', width: 100,
      render: (_: unknown, r: CandidateResponse) =>
        r.status === 'active' ? (
          <Popconfirm title="确定移出？" onConfirm={() => handleRemove(r.id)}>
            <Button size="small" danger>移出</Button>
          </Popconfirm>
        ) : null,
    },
  ];

  return (
    <div>
      <PageHeader title="候选池" enLabel="Candidates" />

      <Space style={{ marginBottom: 16 }}>
        <Input.Search
          placeholder="搜索代码/名称/预案"
          allowClear
          style={{ width: 220 }}
          prefix={<SearchOutlined />}
          value={keyword}
          onChange={e => setKeyword(e.target.value)}
        />
        <Badge count={activeFilterCount} size="small">
          <Button
            icon={<FilterOutlined />}
            onClick={() => setFilterOpen(!filterOpen)}
          >
            筛选
          </Button>
        </Badge>
        <Select
          style={{ width: 120 }}
          value={filter.status}
          onChange={v => setFilterField('status', v)}
          options={[
            { value: 'active', label: '活跃' },
            { value: 'removed', label: '已移出' },
            { value: '', label: '全部' },
          ]}
        />
      </Space>

      <Collapse
        activeKey={filterOpen ? ['filters'] : []}
        onChange={() => setFilterOpen(!filterOpen)}
        ghost
        items={[{
          key: 'filters',
          label: null,
          children: (
            <div style={{ marginBottom: 16, padding: '12px 16px', background: 'var(--bg-secondary, #fafafa)', borderRadius: 8 }}>
              <Row gutter={[12, 12]}>
                <Col span={6}>
                  <Select
                    placeholder="所属计划"
                    allowClear
                    style={{ width: '100%' }}
                    value={filter.planId}
                    onChange={v => setFilterField('planId', v)}
                    options={plans.map(p => ({ value: p.id, label: p.name }))}
                  />
                </Col>
                <Col span={6}>
                  <Select
                    placeholder="行业"
                    allowClear
                    showSearch
                    style={{ width: '100%' }}
                    value={filter.industry}
                    onChange={v => setFilterField('industry', v)}
                    options={industryOptions}
                  />
                </Col>
                <Col span={6}>
                  <Select
                    placeholder="安全主题"
                    allowClear
                    style={{ width: '100%' }}
                    value={filter.securityTheme}
                    onChange={v => setFilterField('securityTheme', v)}
                    options={SECURITY_THEME_OPTIONS}
                  />
                </Col>
                <Col span={6}>
                  <Select
                    placeholder="象限"
                    allowClear
                    style={{ width: '100%' }}
                    value={filter.quadrant}
                    onChange={v => setFilterField('quadrant', v)}
                    options={QUADRANT_OPTIONS}
                  />
                </Col>
                <Col span={6}>
                  <Select
                    placeholder="评级"
                    allowClear
                    style={{ width: '100%' }}
                    value={filter.tier}
                    onChange={v => setFilterField('tier', v)}
                    options={TIER_OPTIONS}
                  />
                </Col>
                <Col span={6}>
                  <Select
                    placeholder="Qiu评分"
                    allowClear
                    style={{ width: '100%' }}
                    value={filter.qiuScore}
                    onChange={v => setFilterField('qiuScore', v)}
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
                    onChange={v => setFilterField('hqRegion', v)}
                    options={hqRegionOptions}
                  />
                </Col>
                <Col span={6}>
                  <Space>
                    <span style={{ color: 'var(--text-secondary, #888)' }}>仅置顶</span>
                    <Switch
                      checked={filter.pinned === true}
                      onChange={v => setFilterField('pinned', v ? true : undefined)}
                    />
                  </Space>
                </Col>
              </Row>
              <div style={{ marginTop: 12, textAlign: 'right' }}>
                <Button onClick={resetFilter}>重置</Button>
              </div>
            </div>
          ),
        }]}
      />

      <Table
        dataSource={filtered}
        columns={columns}
        rowKey="id"
        loading={loading}
        size="small"
        pagination={{ pageSize: 20, showSizeChanger: false }}
      />
    </div>
  );
}
