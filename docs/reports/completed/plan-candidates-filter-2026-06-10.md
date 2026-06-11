# 候选池筛选增强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为候选池页面增加 7 个筛选条件（行业、安全主题、象限、评级、Qiu评分、总部地区、是否置顶），采用前端内存筛选 + 可折叠筛选面板交互。

**Architecture:** 后端扩展 CandidateResponse schema 增加 Stock 字段；前端加载全量数据后用 useMemo 内存过滤，可折叠面板展示筛选项。

**Tech Stack:** Python/FastAPI/Pydantic (backend), React 19/TypeScript/Ant Design (frontend)

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `backend/app/schemas/candidate.py` | 新增 5 个 Stock 字段到 CandidateResponse |
| Modify | `backend/app/routers/candidates.py` | _to_response 映射新字段，移除 import json 到文件顶部 |
| Modify | `frontend/src/api/types.ts` | CandidateResponse 接口新增 5 个字段 |
| Modify | `frontend/src/pages/CandidatesPage.tsx` | 重构为前端筛选 + 可折叠面板 |

---

### Task 1: 扩展后端 CandidateResponse Schema

**Files:**
- Modify: `backend/app/schemas/candidate.py:10-22`

- [ ] **Step 1: 新增字段到 CandidateResponse**

在 `CandidateResponse` 类的 `stock_industry` 之后添加 5 个字段：

```python
class CandidateResponse(BaseModel):
    id: int
    plan_id: int
    plan_name: str = ""
    stock_code: str
    stock_name: str = ""
    stock_industry: Optional[str] = None
    stock_security_theme: Optional[str] = None
    stock_quadrant: Optional[str] = None
    stock_tier: Optional[str] = None
    stock_qiu_score: int = 0
    stock_hq_region: Optional[str] = None
    status: Literal["active", "removed", "promoted"]
    first_seen_at: Any = None
    last_confirmed_at: Any = None
    last_eval: Optional[dict] = None
    pinned: bool
    notes: Optional[str] = None
```

- [ ] **Step 2: 运行后端测试确认无破坏**

Run: `cd backend && source .venv/bin/activate && pytest -x -q`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/candidate.py
git commit -m "feat: add stock fields to CandidateResponse schema"
```

---

### Task 2: 更新 _to_response 映射

**Files:**
- Modify: `backend/app/routers/candidates.py:14-37`

- [ ] **Step 1: 移动 import json 到顶部 + 补充新字段映射**

将 `import json` 从函数内部移到文件顶部。在 `_to_response` 中补充新字段：

```python
"""Candidate CRUD router."""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.candidate import Candidate
from app.services import candidate_service
from app.schemas.candidate import CandidatePromote, CandidateResponse, CandidateUpdate

router = APIRouter(prefix="/api/candidates", tags=["candidates"])


def _to_response(c: Candidate) -> CandidateResponse:
    stock = c.stock
    plan = c.plan
    last_eval = None
    if c.last_eval_json:
        try:
            last_eval = json.loads(c.last_eval_json)
        except Exception:
            pass
    return CandidateResponse(
        id=c.id,
        plan_id=c.plan_id,
        plan_name=plan.name if plan else "",
        stock_code=c.stock_code,
        stock_name=stock.name if stock else "",
        stock_industry=stock.industry if stock else None,
        stock_security_theme=stock.security_theme if stock else None,
        stock_quadrant=stock.quadrant if stock else None,
        stock_tier=stock.tier if stock else None,
        stock_qiu_score=stock.qiu_score if stock else 0,
        stock_hq_region=stock.hq_region if stock else None,
        status=c.status,
        first_seen_at=c.first_seen_at,
        last_confirmed_at=c.last_confirmed_at,
        last_eval=last_eval,
        pinned=c.pinned,
        notes=c.notes,
    )
```

- [ ] **Step 2: 运行后端测试确认无破坏**

Run: `cd backend && source .venv/bin/activate && pytest -x -q`
Expected: All tests pass

- [ ] **Step 3: 启动后端手动验证 API 返回新字段**

Run: `cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 3001`
Then: `curl -s http://localhost:3001/api/candidates | python3 -m json.tool | head -30`
Expected: 响应中包含 `stock_security_theme`、`stock_quadrant`、`stock_tier`、`stock_qiu_score`、`stock_hq_region` 字段

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/candidates.py
git commit -m "feat: map stock fields in candidate _to_response"
```

---

### Task 3: 更新前端 TypeScript 类型

**Files:**
- Modify: `frontend/src/api/types.ts:704-717`

- [ ] **Step 1: 扩展 CandidateResponse 接口**

```typescript
export interface CandidateResponse {
  id: number;
  plan_id: number;
  plan_name: string;
  stock_code: string;
  stock_name: string;
  stock_industry: string | null;
  stock_security_theme: string | null;
  stock_quadrant: string | null;
  stock_tier: string | null;
  stock_qiu_score: number;
  stock_hq_region: string | null;
  status: 'active' | 'removed' | 'promoted';
  first_seen_at: string | null;
  last_confirmed_at: string | null;
  last_eval: Record<string, { passed: boolean; details: string[] }> | null;
  pinned: boolean;
  notes: string | null;
}
```

- [ ] **Step 2: 确认前端构建通过**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/types.ts
git commit -m "feat: add stock fields to CandidateResponse type"
```

---

### Task 4: 重构 CandidatesPage 为前端筛选 + 可折叠面板

**Files:**
- Modify: `frontend/src/pages/CandidatesPage.tsx`

- [ ] **Step 1: 重写 CandidatesPage 组件**

核心变更：
1. 数据加载改为一次性获取全量候选（去掉 plan_id/status query params），筛选取消后端过滤
2. 新增 7 个筛选 state + useMemo 过滤逻辑
3. 可折叠筛选面板 UI

```tsx
import { useEffect, useState, useMemo } from 'react';
import {
  Table, Tag, Button, Space, Select, Modal, Typography, Tooltip, Popconfirm,
  Collapse, Row, Col, Switch, Badge,
} from 'antd';
import { PushpinOutlined, PushpinFilled, ArrowUpOutlined, FilterOutlined } from '@ant-design/icons';
import { useAntdStatic } from '../hooks/useAntdStatic';
import PageHeader from '../components/PageHeader';
import { listCandidates, promoteCandidate, updateCandidate, removeCandidate, listPlans, listWatchlistGroups } from '../api/client';
import type { CandidateResponse, PlanResponse, WatchlistGroupResponse } from '../api/types';

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  active: { color: 'green', label: '活跃' },
  removed: { color: 'red', label: '已移出' },
  promoted: { color: 'blue', label: '已提升' },
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
  { value: 'heaven', label: '天罡' },
  { value: 'mystic', label: '地煞' },
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

const EMPTY_FILTER: FilterState = {
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
  const [groups, setGroups] = useState<WatchlistGroupResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<FilterState>(EMPTY_FILTER);
  const [filterOpen, setFilterOpen] = useState(false);
  const [promoteModal, setPromoteModal] = useState<CandidateResponse | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const [cs, ps, gs] = await Promise.all([
        listCandidates({}),
        listPlans(),
        listWatchlistGroups(),
      ]);
      setCandidates(cs);
      setPlans(ps);
      setGroups(gs);
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
    return candidates.filter(c => {
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
  }, [candidates, filter]);

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

  const resetFilter = () => setFilter(EMPTY_FILTER);

  const handlePromote = async () => {
    if (!promoteModal || !selectedGroup) return;
    try {
      await promoteCandidate(promoteModal.id, selectedGroup);
      message.success(`${promoteModal.stock_code} 已提升到自选股`);
      setPromoteModal(null);
      load();
    } catch { message.error('提升失败'); }
  };

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
      title: '操作', width: 140,
      render: (_: unknown, r: CandidateResponse) =>
        r.status === 'active' ? (
          <Space size="small">
            <Button size="small" type="primary" icon={<ArrowUpOutlined />}
              onClick={() => setPromoteModal(r)}>提升</Button>
            <Popconfirm title="确定移出？" onConfirm={() => handleRemove(r.id)}>
              <Button size="small" danger>移出</Button>
            </Popconfirm>
          </Space>
        ) : null,
    },
  ];

  return (
    <div>
      <PageHeader title="候选池" enLabel="Candidates" />

      <Space style={{ marginBottom: 16 }}>
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
            { value: 'promoted', label: '已提升' },
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

      <Modal title={`提升 ${promoteModal?.stock_code} 到自选股`}
        open={!!promoteModal}
        onOk={handlePromote}
        onCancel={() => setPromoteModal(null)}>
        <div style={{ marginBottom: 16 }}>
          <Typography.Text>选择自选股分组：</Typography.Text>
        </div>
        <Select style={{ width: '100%' }} placeholder="选择分组"
          value={selectedGroup} onChange={setSelectedGroup}
          options={groups.map(g => ({ value: g.id, label: g.name }))} />
      </Modal>
    </div>
  );
}
```

- [ ] **Step 2: 确认前端构建通过**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: 启动前后端，在浏览器验证**

Run: `./dev.sh`
Open: `http://localhost:3000/candidates`
验证：
- 页面加载正常，表格数据正确
- 「筛选」按钮点击展开/收起面板
- 各筛选条件独立工作
- 多个筛选条件 AND 组合正确
- 重置按钮清空所有筛选
- 提升到自选股等原有功能不受影响

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/CandidatesPage.tsx
git commit -m "feat: add collapsible filter panel with 7 new filter conditions to candidates page"
```
