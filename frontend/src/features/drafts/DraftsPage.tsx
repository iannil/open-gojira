import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, Modal, Popconfirm, Select, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';

import { PageHeader, FilterBar, EmptyState, StatCard } from '../../components/primitives';
import QueryBoundary from '../../components/QueryBoundary';
import DisciplineChecklistModal from '../../components/DisciplineChecklistModal';
import { fetchUniverse } from '../../api/client';
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

export default function DraftsPage() {
  const [statusFilter, setStatusFilter] = useState<DraftListFilter['status']>('pending');
  const [codeFilter, setCodeFilter] = useState<string>('');
  const [disciplineTarget, setDisciplineTarget] = useState<DisciplineTarget | null>(null);

  const filter = useMemo<DraftListFilter>(
    () => ({
      status: statusFilter,
      code: codeFilter.trim() || undefined,
      limit: 200,
    }),
    [statusFilter, codeFilter],
  );

  const draftsQ = useDraftsQuery(filter);
  // Universe fetch builds a code → name map for display. Long stale window
  // since universe rarely changes within a session.
  const universeQ = useQuery({
    queryKey: ['universe', 'name-map'],
    queryFn: fetchUniverse,
    staleTime: 5 * 60_000,
  });
  const executeM = useExecuteDraftMutation();
  const cancelM = useCancelDraftMutation();

  const drafts = draftsQ.data ?? [];
  const nameMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const u of universeQ.data ?? []) m.set(u.code, u.name);
    return m;
  }, [universeQ.data]);

  const pendingCount = drafts.filter((d) => d.status === 'pending').length;
  const buyCount = drafts.filter((d) => d.status === 'pending' && d.side === 'BUY').length;
  const sellCount = drafts.filter((d) => d.status === 'pending' && d.side === 'SELL').length;

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

  const columns: ColumnsType<DraftResponse> = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 60,
      render: (v: number) => <span className="num">{v}</span>,
    },
    {
      title: '代码',
      dataIndex: 'code',
      width: 160,
      render: (v: string) => (
        <Link to={`/stock/${v}`}>
          <Text code>{v}</Text>
          {nameMap.get(v) && (
            <Text type="secondary" style={{ marginLeft: 'var(--sp-2)' }}>
              {nameMap.get(v)}
            </Text>
          )}
        </Link>
      ),
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

  // Quiet empty state only when filter is "pending" (default) and there are no pending drafts.
  // Cold empty state when user has no drafts at all (would show when filter=executed also empty).
  // Filter empty when filter applied but no match.
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
          <StatCard label="待执行" value={pendingCount} />
          <StatCard label="待买入" value={buyCount} />
          <StatCard label="待卖出" value={sellCount} />
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
          style={{ width: 180 }}
          onChange={(v) => setCodeFilter(v ?? '')}
          options={Array.from(new Set(drafts.map((d) => d.code))).map((c) => ({
            value: c,
            label: c,
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
          <Table<DraftResponse>
            columns={columns}
            dataSource={drafts}
            rowKey="id"
            loading={draftsQ.isFetching && !draftsQ.data}
            size="small"
            pagination={{ pageSize: 20, showSizeChanger: false }}
            scroll={{ x: 1100 }}
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
