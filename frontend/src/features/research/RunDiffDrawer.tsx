import { useState } from 'react';
import {
  Drawer,
  Spin,
  Tabs,
  Typography,
  Alert,
  Tag,
  Table,
  Card,
  Empty,
} from 'antd';
import { useQuery } from '@tanstack/react-query';
import { getResearchRunDiff } from '../../api/client';
import type {
  ResearchClaimDiffItem,
  ResearchRunDiff,
  ResearchScarceLayerDiffItem,
} from '../../api/types';

interface Props {
  runAId: number;
  runBId: number;
  onClose: () => void;
}

const CATEGORY_COLORS: Record<string, string> = {
  promoted: 'green',
  demoted: 'red',
  new_in: 'green',
  dropped: 'red',
  unchanged: 'default',
  new_risk: 'red',
  resolved: 'green',
  tightened: 'orange',
  loosened: 'gold',
  entered: 'green',
  exited: 'red',
  reranked: 'orange',
};

const CATEGORY_LABELS: Record<string, string> = {
  promoted: '↑ 升',
  demoted: '↓ 降',
  new_in: '+ 新进',
  dropped: '- 退出',
  unchanged: '— 不变',
  new_risk: '+ 新风险',
  resolved: '✓ 已解除',
  tightened: '⚠ 收紧',
  loosened: '↘ 放松',
  entered: '+ 进入',
  exited: '- 退出',
  reranked: '⇄ 重排',
};

export function RunDiffDrawer({ runAId, runBId, onClose }: Props) {
  const diffQ = useQuery({
    queryKey: ['research-run-diff', runAId, runBId],
    queryFn: () => getResearchRunDiff(runAId, runBId),
    enabled: !!runAId && !!runBId,
  });

  const [activeTab, setActiveTab] = useState('ranking');

  return (
    <Drawer
      title={`Run ${runAId} vs ${runBId} — 差异对比`}
      open
      onClose={onClose}
      width="80%"
      destroyOnClose
    >
      {diffQ.isLoading && <Spin tip="加载差异..." />}
      {diffQ.isError && (
        <Alert
          type="error"
          message="加载差异失败"
          description={String(diffQ.error ?? '')}
        />
      )}
      {diffQ.data && (
        <DiffContent
          diff={diffQ.data}
          activeTab={activeTab}
          onTabChange={setActiveTab}
        />
      )}
    </Drawer>
  );
}

function DiffContent({
  diff,
  activeTab,
  onTabChange,
}: {
  diff: ResearchRunDiff;
  activeTab: string;
  onTabChange: (k: string) => void;
}) {
  const aLabel = `Run ${diff.run_a.id}`;
  const bLabel = `Run ${diff.run_b.id}`;
  const aTime = new Date(diff.run_a.started_at).toLocaleDateString('zh-CN');
  const bTime = new Date(diff.run_b.started_at).toLocaleDateString('zh-CN');

  return (
    <div>
      {diff.degradations.length > 0 && (
        <Alert
          style={{ marginBottom: 16 }}
          type="warning"
          message="部分维度降级"
          description={
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {diff.degradations.map((d) => <li key={d}>{d}</li>)}
            </ul>
          }
        />
      )}

      <Card size="small" style={{ marginBottom: 16 }}>
        <Typography.Text strong>
          {aLabel} ({aTime}) → {bLabel} ({bTime})
        </Typography.Text>
        <div style={{ marginTop: 8, display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          <SummaryBlock
            title="排名"
            data={[
              ['↑', diff.summary.ranking.promoted, 'green'],
              ['↓', diff.summary.ranking.demoted, 'red'],
              ['+', diff.summary.ranking.new_in, 'green'],
              ['-', diff.summary.ranking.dropped, 'red'],
            ]}
          />
          <SummaryBlock
            title="失败条件"
            data={
              diff.claims_diff
                ? [
                    ['+', diff.summary.claims.new_risks, 'red'],
                    ['✓', diff.summary.claims.resolved, 'green'],
                    ['⚠', diff.summary.claims.tightened, 'orange'],
                  ]
                : [['—', 0, 'default']]
            }
          />
          <SummaryBlock
            title="稀缺层"
            data={[
              ['+', diff.summary.scarce_layers.entered, 'green'],
              ['-', diff.summary.scarce_layers.exited, 'red'],
              ['⇄', diff.summary.scarce_layers.reranked, 'orange'],
            ]}
          />
        </div>
      </Card>

      <Tabs
        activeKey={activeTab}
        onChange={onTabChange}
        items={[
          {
            key: 'ranking',
            label: `排名 (${diff.summary.ranking.promoted + diff.summary.ranking.demoted + diff.summary.ranking.new_in + diff.summary.ranking.dropped} 变)`,
            children: <RankingTable diff={diff.ranking_diff} aLabel={aLabel} bLabel={bLabel} />,
          },
          {
            key: 'claims',
            label: diff.claims_diff
              ? `失败条件 (${diff.summary.claims.new_risks + diff.summary.claims.resolved + diff.summary.claims.tightened} 变)`
              : '失败条件 (legacy)',
            children: diff.claims_diff
              ? <ClaimsGrid diff={diff.claims_diff} aLabel={aLabel} bLabel={bLabel} />
              : <Empty description="其中一个 Run 是 legacy,无 structured claims" />,
          },
          {
            key: 'scarce',
            label: `稀缺层 (${diff.summary.scarce_layers.entered + diff.summary.scarce_layers.exited + diff.summary.scarce_layers.reranked} 变)`,
            children: <ScarceLayersChart diff={diff.scarce_layers_diff} aLabel={aLabel} bLabel={bLabel} />,
          },
        ]}
      />
    </div>
  );
}

function SummaryBlock({ title, data }: { title: string; data: (string | number)[][] }) {
  return (
    <div>
      <Typography.Text type="secondary">{title}</Typography.Text>
      <div style={{ marginTop: 4 }}>
        {data.map(([label, count, color]) => (
          <Tag key={label as string} color={color as string} style={{ marginRight: 8 }}>
            {label} {count}
          </Tag>
        ))}
      </div>
    </div>
  );
}

// ── Ranking ────────────────────────────────────────────────────────────

function RankingTable({
  diff,
  aLabel,
  bLabel,
}: {
  diff: ResearchRunDiff['ranking_diff'];
  aLabel: string;
  bLabel: string;
}) {
  const all = [
    ...diff.promoted,
    ...diff.demoted,
    ...diff.new_in,
    ...diff.dropped,
    ...diff.unchanged,
  ].sort((x, y) => {
    // Sort by run_b rank (or run_a rank if dropped), unchanged last
    const ra = x.rank_to ?? x.rank_from ?? 99;
    const rb = y.rank_to ?? y.rank_from ?? 99;
    return ra - rb;
  });

  return (
    <Table
      rowKey={(r) => `${r.stock_code}-${r.category}`}
      dataSource={all}
      pagination={false}
      size="small"
      columns={[
        {
          title: '变化', dataIndex: 'category', width: 100,
          render: (c: string) => (
            <Tag color={CATEGORY_COLORS[c]}>{CATEGORY_LABELS[c]}</Tag>
          ),
        },
        { title: 'Code', dataIndex: 'stock_code', width: 100 },
        { title: 'Name', dataIndex: 'name' },
        {
          title: aLabel, dataIndex: 'rank_from', width: 100, align: 'center',
          render: (v: number | null) => v ?? '—',
        },
        {
          title: bLabel, dataIndex: 'rank_to', width: 100, align: 'center',
          render: (v: number | null) => v ?? '—',
        },
        {
          title: 'Δ', dataIndex: 'delta', width: 60, align: 'center',
          render: (v: number | null) => {
            if (v === null) return '';
            if (v < 0) return <Typography.Text type="success">{v}</Typography.Text>;
            if (v > 0) return <Typography.Text type="danger">+{v}</Typography.Text>;
            return '—';
          },
        },
      ]}
    />
  );
}

// ── Claims ─────────────────────────────────────────────────────────────

function ClaimsGrid({
  diff,
  aLabel,
  bLabel,
}: {
  diff: ResearchRunDiff['claims_diff'];
  aLabel: string;
  bLabel: string;
}) {
  if (!diff) return null;
  const all = [
    ...diff.new_risks,
    ...diff.resolved,
    ...diff.tightened,
    ...diff.loosened,
    ...diff.unchanged,
  ];

  if (all.length === 0) {
    return <Empty description="无失败条件可对比" />;
  }

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      {all.map((item) => (
        <ClaimCard key={item.subject} item={item} aLabel={aLabel} bLabel={bLabel} />
      ))}
    </div>
  );
}

function ClaimCard({
  item,
  aLabel,
  bLabel,
}: {
  item: ResearchClaimDiffItem;
  aLabel: string;
  bLabel: string;
}) {
  return (
    <Card size="small">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <Typography.Text strong>{item.subject}</Typography.Text>
        <Tag color={CATEGORY_COLORS[item.category]}>
          {CATEGORY_LABELS[item.category]}
        </Tag>
      </div>
      <Row12 aLabel={aLabel} snapshot={item.claim_from} />
      <Row12 aLabel={bLabel} snapshot={item.claim_to} />
    </Card>
  );
}

function Row12({
  aLabel,
  snapshot,
}: {
  aLabel: string;
  snapshot: ResearchClaimDiffItem['claim_to'];
}) {
  if (!snapshot) {
    return (
      <div style={{ padding: '4px 0', color: '#999' }}>
        {aLabel}: —
      </div>
    );
  }
  return (
    <div style={{ padding: '4px 0' }}>
      <Typography.Text type="secondary">{aLabel}: </Typography.Text>
      <span>{snapshot.predicate}</span>
      {snapshot.signal && (
        <Tag color="blue" style={{ marginLeft: 8 }}>{snapshot.signal}</Tag>
      )}
      <span style={{ marginLeft: 8, color: '#666' }}>{snapshot.outcome}</span>
    </div>
  );
}

// ── Scarce Layers ──────────────────────────────────────────────────────

function ScarceLayersChart({
  diff,
  aLabel,
  bLabel,
}: {
  diff: ResearchRunDiff['scarce_layers_diff'];
  aLabel: string;
  bLabel: string;
}) {
  const all: ResearchScarceLayerDiffItem[] = [
    ...diff.entered,
    ...diff.exited,
    ...diff.reranked,
    ...diff.unchanged,
  ].sort((a, b) => a.layer_index - b.layer_index);

  if (all.length === 0) {
    return <Empty description="无稀缺层数据" />;
  }

  return (
    <Table
      rowKey={(r) => `${r.layer_index}-${r.category}`}
      dataSource={all}
      pagination={false}
      size="small"
      columns={[
        {
          title: '变化', dataIndex: 'category', width: 100,
          render: (c: string) => (
            <Tag color={CATEGORY_COLORS[c]}>{CATEGORY_LABELS[c]}</Tag>
          ),
        },
        {
          title: '层', dataIndex: 'layer_index', width: 60, align: 'center',
          render: (v: number) => `L${v}`,
        },
        { title: '层名', dataIndex: 'layer_name' },
        {
          title: aLabel, dataIndex: 'rank_from', width: 100, align: 'center',
          render: (v: number | null) => v ?? '—',
        },
        {
          title: bLabel, dataIndex: 'rank_to', width: 100, align: 'center',
          render: (v: number | null) => v ?? '—',
        },
      ]}
    />
  );
}
