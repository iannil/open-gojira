import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, Modal, Popconfirm, Select, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';

import { PageHeader, FilterBar, EmptyState, StatCard } from '../../components/primitives';
import QueryBoundary from '../../components/QueryBoundary';
import DisciplineChecklistModal from '../../components/DisciplineChecklistModal';
import { defaultPagination } from '../../lib/pagination';
import { fetchCockpit } from '../../api/client';
import { useDraftsQuery } from './useDraftQueries';
import {
  useCancelDraftMutation,
  useExecuteDraftMutation,
} from './useDraftMutations';
import { type DraftListFilter } from './queries';
import type { DraftResponse } from '../../api/types';

const { Text } = Typography;

const SIDE_COLOR: Record<'BUY' | 'SELL', string> = {
  BUY: 'green',
  SELL: 'red',
};

const SIDE_LABEL: Record<'BUY' | 'SELL', string> = {
  BUY: '买入',
  SELL: '卖出',
};

const STATUS_META: Record<
  DraftResponse['status'],
  { color: string; label: string }
> = {
  pending: { color: 'blue', label: '待执行' },
  executed: { color: 'green', label: '已成交' },
  cancelled: { color: 'default', label: '已取消' },
};

const STEP_KIND_LABEL: Record<string, string> = {
  buy_ladder: '买入档位',
  sell_ladder: '卖出档位',
  rebalance: '再平衡',
};

interface DisciplineTarget {
  id: number;
  side: 'BUY' | 'SELL';
  code: string;
  tier: string | null;
  theme: string | null;
  suggestedQuantity: number | null;
}

/** One row per unique stock code. Aggregates the underlying drafts. */
interface DraftGroup {
  code: string;
  name: string | undefined;
  drafts: DraftResponse[];
  count: number;
  buyCount: number;
  sellCount: number;
  pendingCount: number;
  totalAddPct: number; // sum of add_pct across BUY drafts (0 if none)
  totalReducePct: number; // sum of reduce_pct_of_position across SELL drafts
  latestTriggeredAt: string | null;
}

export default function DraftsPage() {
  const [statusFilter, setStatusFilter] = useState<DraftListFilter['status']>('pending');
  const [codeFilter, setCodeFilter] = useState<string>('');
  const [disciplineTarget, setDisciplineTarget] = useState<DisciplineTarget | null>(null);

  const filter = useMemo<DraftListFilter>(
    () => ({
      status: statusFilter,
      code: codeFilter.trim() || undefined,
      limit: 500,
    }),
    [statusFilter, codeFilter],
  );

  const draftsQ = useDraftsQuery(filter);
  // Cockpit carries stock_name on each draft — piggyback to build a
  // code→name map. fetchUniverse() returns 0 in full_coverage mode (no
  // curated subscription), so this is the most reliable name source
  // without a backend change to DraftResponse.
  const cockpitQ = useQuery({
    queryKey: ['cockpit', 'name-map'],
    queryFn: fetchCockpit,
    staleTime: 60_000,
  });
  const executeM = useExecuteDraftMutation();
  const cancelM = useCancelDraftMutation();

  const drafts = draftsQ.data ?? [];
  const nameMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const d of cockpitQ.data?.drafts ?? []) {
      if (d.stock_name) m.set(d.code, d.stock_name);
    }
    return m;
  }, [cockpitQ.data]);

  // Group drafts by code (merge same stocks)
  const groups: DraftGroup[] = useMemo(() => {
    const byCode = new Map<string, DraftResponse[]>();
    for (const d of drafts) {
      const arr = byCode.get(d.code) ?? [];
      arr.push(d);
      byCode.set(d.code, arr);
    }
    const result: DraftGroup[] = [];
    for (const [code, groupDrafts] of byCode) {
      const buyCount = groupDrafts.filter((d) => d.side === 'BUY').length;
      const sellCount = groupDrafts.filter((d) => d.side === 'SELL').length;
      const pendingCount = groupDrafts.filter((d) => d.status === 'pending').length;
      const totalAddPct = groupDrafts
        .filter((d) => d.side === 'BUY' && d.add_pct != null)
        .reduce((s, d) => s + (d.add_pct ?? 0), 0);
      const totalReducePct = groupDrafts
        .filter((d) => d.side === 'SELL' && d.reduce_pct_of_position != null)
        .reduce((s, d) => s + (d.reduce_pct_of_position ?? 0), 0);
      const times = groupDrafts
        .map((d) => d.triggered_at)
        .filter((t): t is string => !!t)
        .sort();
      result.push({
        code,
        name: nameMap.get(code),
        drafts: groupDrafts.sort((a, b) => a.id - b.id),
        count: groupDrafts.length,
        buyCount,
        sellCount,
        pendingCount,
        totalAddPct,
        totalReducePct,
        latestTriggeredAt: times.length ? times[times.length - 1] : null,
      });
    }
    // Sort by draft count desc, then by code
    return result.sort((a, b) => b.count - a.count || a.code.localeCompare(b.code));
  }, [drafts, nameMap]);

  const pendingTotal = drafts.filter((d) => d.status === 'pending').length;
  const buyTotal = drafts.filter((d) => d.status === 'pending' && d.side === 'BUY').length;
  const sellTotal = drafts.filter((d) => d.status === 'pending' && d.side === 'SELL').length;

  const handleReset = () => {
    setStatusFilter('pending');
    setCodeFilter('');
  };

  const handleExecuteClick = (draft: DraftResponse) => {
    setDisciplineTarget({
      id: draft.id,
      side: draft.side,
      code: draft.code,
      tier: null,
      theme: null,
      suggestedQuantity: null,
    });
  };

  const handleDisciplineConfirm = async (
    checklist: Record<string, boolean>,
    fill: { price: number; quantity: number },
  ) => {
    if (!disciplineTarget) return;
    await executeM.mutateAsync({
      id: disciplineTarget.id,
      payload: {
        discipline_checklist: checklist,
        buy_price: fill.price,
        quantity: fill.quantity,
      },
    });
    setDisciplineTarget(null);
  };

  const handleCancel = (id: number) => {
    Modal.confirm({
      title: '取消该订单草稿？',
      content: '取消后该档位可在下一次评估时重新触发。',
      okText: '取消草稿',
      cancelText: '保留',
      okButtonProps: { danger: true },
      onOk: () => cancelM.mutateAsync(id),
    });
  };

  // ── Inner draft table (shown when a group row is expanded) ──────────
  const draftColumns: ColumnsType<DraftResponse> = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 60,
      render: (v: number) => <span className="num">{v}</span>,
    },
    {
      title: '方向',
      dataIndex: 'side',
      width: 80,
      render: (s: 'BUY' | 'SELL') => <Tag color={SIDE_COLOR[s]}>{SIDE_LABEL[s]}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (s: DraftResponse['status']) => (
        <Tag color={STATUS_META[s].color}>{STATUS_META[s].label}</Tag>
      ),
    },
    {
      title: '档位',
      width: 130,
      render: (_: unknown, r: DraftResponse) => (
        <span>
          {STEP_KIND_LABEL[r.step_kind] ?? r.step_kind}
          {r.step_index != null && (
            <Text type="secondary" style={{ marginLeft: 4 }}>
              #<span className="num">{r.step_index}</span>
            </Text>
          )}
        </span>
      ),
    },
    {
      title: '仓位调整',
      width: 130,
      render: (_: unknown, r: DraftResponse) => {
        if (r.add_pct != null) {
          return (
            <span className="num" style={{ color: 'var(--green-600)' }}>
              +{(r.add_pct * 100).toFixed(1)}%
            </span>
          );
        }
        if (r.reduce_pct_of_position != null) {
          return (
            <span className="num" style={{ color: 'var(--red-600)' }}>
              -{(r.reduce_pct_of_position * 100).toFixed(1)}%
            </span>
          );
        }
        return '—';
      },
    },
    {
      title: '触发时间',
      dataIndex: 'triggered_at',
      width: 160,
      render: (v: string | null) =>
        v ? (
          <span
            className="num"
            style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}
          >
            {dayjs(v).format('MM-DD HH:mm:ss')}
          </span>
        ) : (
          '—'
        ),
    },
    {
      title: '原因',
      dataIndex: 'reason',
      ellipsis: true,
      render: (v: string) => (
        <Text type="secondary" style={{ fontSize: 'var(--fs-xs)' }}>
          {v}
        </Text>
      ),
    },
    {
      title: '操作',
      width: 130,
      fixed: 'right',
      render: (_: unknown, r: DraftResponse) =>
        r.status === 'pending' ? (
          <>
            <Button
              size="small"
              type="primary"
              onClick={() => handleExecuteClick(r)}
              loading={executeM.isPending}
            >
              执行
            </Button>
            <Popconfirm
              title="取消该草稿？"
              description="该档位可在下次评估时重新触发"
              okText="取消草稿"
              cancelText="保留"
              okButtonProps={{ danger: true }}
              onConfirm={() => handleCancel(r.id)}
            >
              <Button size="small" type="link" danger loading={cancelM.isPending}>
                取消
              </Button>
            </Popconfirm>
          </>
        ) : (
          <Text type="secondary" style={{ fontSize: 'var(--fs-xs)' }}>
            —
          </Text>
        ),
    },
  ];

  // ── Outer group table ───────────────────────────────────────────────
  const groupColumns: ColumnsType<DraftGroup> = [
    {
      title: '代码',
      dataIndex: 'code',
      width: 180,
      render: (v: string, r: DraftGroup) => (
        <Link to={`/stock/${v}`}>
          <Text code>{v}</Text>
          {r.name && (
            <Text type="secondary" style={{ marginLeft: 'var(--sp-2)' }}>
              {r.name}
            </Text>
          )}
        </Link>
      ),
    },
    {
      title: '草稿数',
      dataIndex: 'count',
      width: 80,
      align: 'right',
      render: (v: number) => <span className="num">{v}</span>,
      sorter: (a, b) => a.count - b.count,
    },
    {
      title: '方向',
      width: 140,
      render: (_: unknown, r: DraftGroup) => (
        <Space size={4}>
          {r.buyCount > 0 && <Tag color="green">买入 <span className="num">{r.buyCount}</span></Tag>}
          {r.sellCount > 0 && <Tag color="red">卖出 <span className="num">{r.sellCount}</span></Tag>}
        </Space>
      ),
    },
    {
      title: '总仓位调整',
      width: 180,
      render: (_: unknown, r: DraftGroup) => (
        <Space size={8}>
          {r.totalAddPct > 0 && (
            <span className="num" style={{ color: 'var(--green-600)' }}>
              +组合 {(r.totalAddPct * 100).toFixed(1)}%
            </span>
          )}
          {r.totalReducePct > 0 && (
            <span className="num" style={{ color: 'var(--red-600)' }}>
              −仓位 {(r.totalReducePct * 100).toFixed(0)}%
            </span>
          )}
          {r.totalAddPct === 0 && r.totalReducePct === 0 && '—'}
        </Space>
      ),
    },
    {
      title: '待执行',
      dataIndex: 'pendingCount',
      width: 80,
      align: 'right',
      render: (v: number) =>
        v > 0 ? (
          <Tag color="blue">
            <span className="num">{v}</span>
          </Tag>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: '最新触发',
      dataIndex: 'latestTriggeredAt',
      width: 160,
      render: (v: string | null) =>
        v ? (
          <span
            className="num"
            style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}
          >
            {dayjs(v).format('MM-DD HH:mm')}
          </span>
        ) : (
          '—'
        ),
    },
  ];

  // Quiet empty state only when filter is "pending" (default) and there are no pending drafts.
  const emptyVariant: 'cold' | 'filter' | 'quiet' =
    statusFilter === 'pending' && !codeFilter
      ? 'quiet'
      : codeFilter || statusFilter
        ? 'filter'
        : 'cold';

  return (
    <div>
      <PageHeader
        title="草稿"
        enLabel="Drafts"
        purpose="预案运行后产出的具体动作（BUY X 股 @ Y 元 / 卖出 X% 仓位）。是「候选池」到「成交流水」之间的中间状态 —— 等你确认纪律检查后才会变成真实成交。"
        flow={[
          { to: '/candidates', label: '候选池' },
          { label: '草稿' },
          { to: '/trades', label: '成交流水' },
        ]}
      />

      {statusFilter === 'pending' && !codeFilter && drafts.length > 0 && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
            gap: 'var(--sp-3)',
            marginBottom: 'var(--sp-4)',
          }}
        >
          <StatCard label="待执行草稿" value={pendingTotal} />
          <StatCard label="待买入" value={buyTotal} />
          <StatCard label="待卖出" value={sellTotal} />
          <StatCard label="涉及股票" value={groups.length} />
        </div>
      )}

      <FilterBar onReset={codeFilter || statusFilter !== 'pending' ? handleReset : undefined}>
        <Select
          value={statusFilter}
          onChange={(v) => setStatusFilter(v as DraftListFilter['status'])}
          style={{ width: 130 }}
          options={[
            { value: 'pending', label: '待执行' },
            { value: 'executed', label: '已成交' },
            { value: 'cancelled', label: '已取消' },
          ]}
        />
        <Select
          value={codeFilter || undefined}
          placeholder="按代码过滤"
          allowClear
          showSearch
          style={{ width: 200 }}
          onChange={(v) => setCodeFilter(v ?? '')}
          options={Array.from(new Set(drafts.map((d) => d.code))).map((c) => ({
            value: c,
            label: nameMap.get(c) ? `${c} · ${nameMap.get(c)}` : c,
          }))}
        />
      </FilterBar>

      <QueryBoundary
        query={draftsQ}
        isEmpty={(data) => data.length === 0}
        emptyRender={
          <EmptyState
            variant={emptyVariant}
            title={
              emptyVariant === 'quiet'
                ? '今日无新信号，预案在监控中'
                : emptyVariant === 'filter'
                  ? '无匹配草稿'
                  : '还没有任何草稿'
            }
            description={
              emptyVariant === 'cold'
                ? '草稿是预案运行后产出的具体买卖动作。先去预案页运行一个预案。'
                : undefined
            }
            cta={
              emptyVariant === 'cold'
                ? { label: '去运行预案', onClick: () => (window.location.href = '/plans') }
                : undefined
            }
            onClearFilter={emptyVariant === 'filter' ? handleReset : undefined}
          />
        }
      >
        {() => (
          <Table<DraftGroup>
            columns={groupColumns}
            dataSource={groups}
            rowKey={(r) => r.code}
            loading={draftsQ.isFetching && !draftsQ.data}
            size="small"
            pagination={{ ...defaultPagination, defaultPageSize: 50 }}
            scroll={{ x: 900 }}
            expandable={{
              rowExpandable: (r) => r.count > 1,
              expandedRowRender: (r) => (
                <Table<DraftResponse>
                  columns={draftColumns}
                  dataSource={r.drafts}
                  rowKey="id"
                  size="small"
                  pagination={false}
                  scroll={{ x: 900 }}
                />
              ),
            }}
          />
        )}
      </QueryBoundary>

      <DisciplineChecklistModal
        open={!!disciplineTarget}
        side={disciplineTarget?.side ?? 'BUY'}
        stockCode={disciplineTarget?.code ?? ''}
        theme={disciplineTarget?.theme ?? null}
        tier={disciplineTarget?.tier ?? null}
        suggestedQuantity={disciplineTarget?.suggestedQuantity ?? null}
        onConfirm={handleDisciplineConfirm}
        onCancel={() => setDisciplineTarget(null)}
      />
    </div>
  );
}
