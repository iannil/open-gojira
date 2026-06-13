import { useState } from 'react';
import { Button, Popconfirm, Space, Switch, Table, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';

import QueryBoundary from '../../../components/QueryBoundary';
import { EmptyState } from '../../../components/primitives';
import { useRiskRulesQuery } from '../useMonitoringQueries';
import {
  useCreateRiskRuleMutation,
  useDeleteRiskRuleMutation,
  useUpdateRiskRuleMutation,
} from '../useMonitoringMutations';
import type {
  HoldingRiskRule,
  RiskRuleCreate,
  RiskRuleUpdate,
  StopLossType,
} from '../../../api/types';
import RiskRuleModal from './RiskRuleModal';

const { Text } = Typography;

const STOP_LOSS_TYPE_LABELS: Record<StopLossType, string> = {
  pct_from_cost: '成本百分比',
  trailing: '追踪止损',
  fixed_price: '固定价格',
};

function formatPct(fraction: number | null | undefined, digits = 1): string {
  if (fraction == null || !Number.isFinite(fraction)) return '—';
  return `${(fraction * 100).toFixed(digits)}%`;
}

export default function RiskRulesTab() {
  const rulesQ = useRiskRulesQuery();
  const createM = useCreateRiskRuleMutation();
  const updateM = useUpdateRiskRuleMutation();
  const deleteM = useDeleteRiskRuleMutation();

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<HoldingRiskRule | null>(null);

  const handleCreate = () => {
    setEditing(null);
    setModalOpen(true);
  };

  const handleEdit = (r: HoldingRiskRule) => {
    setEditing(r);
    setModalOpen(true);
  };

  const handleSave = async (payload: RiskRuleCreate & { peak_price?: number | null }) => {
    if (editing) {
      const update: RiskRuleUpdate = {
        stop_loss_pct: payload.stop_loss_pct,
        stop_loss_type: payload.stop_loss_type,
        take_profit_pct: payload.take_profit_pct,
        take_profit_type: payload.take_profit_type,
        peak_price: payload.peak_price,
        enabled: payload.enabled,
      };
      await updateM.mutateAsync({ id: editing.id, payload: update });
    } else {
      await createM.mutateAsync(payload);
    }
    setModalOpen(false);
  };

  const columns: ColumnsType<HoldingRiskRule> = [
    {
      title: '股票代码',
      dataIndex: 'stock_code',
      width: 120,
      render: (v: string) => <code style={{ fontSize: 'var(--fs-sm)' }}>{v}</code>,
    },
    {
      title: '止损',
      width: 180,
      render: (_: unknown, r: HoldingRiskRule) => (
        <span>
          <Tag color={r.stop_loss_pct == null ? 'default' : 'orange'}>
            <span className="num">{formatPct(r.stop_loss_pct)}</span>
          </Tag>
          <Text type="secondary" style={{ fontSize: 'var(--fs-xs)' }}>
            {STOP_LOSS_TYPE_LABELS[r.stop_loss_type] ?? r.stop_loss_type}
          </Text>
        </span>
      ),
    },
    {
      title: '止盈',
      width: 140,
      render: (_: unknown, r: HoldingRiskRule) => (
        <Tag color={r.take_profit_pct == null ? 'default' : 'green'}>
          <span className="num">{formatPct(r.take_profit_pct)}</span>
        </Tag>
      ),
    },
    {
      title: '追踪峰值',
      dataIndex: 'peak_price',
      width: 110,
      render: (v: number | null) =>
        v == null ? (
          '—'
        ) : (
          <span className="num">¥{v.toFixed(2)}</span>
        ),
    },
    {
      title: '状态',
      width: 140,
      render: (_: unknown, r: HoldingRiskRule) =>
        r.triggered_at ? (
          <Tooltip title={r.trigger_reason ?? ''}>
            <Tag color="red">已触发</Tag>
          </Tooltip>
        ) : r.enabled ? (
          <Tag color="success">监控中</Tag>
        ) : (
          <Tag>已停用</Tag>
        ),
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      width: 80,
      render: (enabled: boolean, record: HoldingRiskRule) => (
        <Switch
          size="small"
          checked={enabled}
          loading={updateM.isPending}
          onChange={(v) => updateM.mutate({ id: record.id, payload: { enabled: v } })}
        />
      ),
    },
    {
      title: '操作',
      width: 140,
      render: (_: unknown, record: HoldingRiskRule) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          />
          <Popconfirm
            title={`确认删除 ${record.stock_code} 的规则?`}
            onConfirm={() => deleteM.mutate(record.id)}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 'var(--sp-3)',
        }}
      >
        <Text type="secondary" style={{ fontSize: 'var(--fs-sm)' }}>
          按持仓股票配置止损/止盈规则。盘中 intraday_price_poll 任务（每 5 分钟）会根据实时价格评估并触发告警。
        </Text>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
          新增规则
        </Button>
      </div>
      <QueryBoundary
        query={rulesQ}
        isEmpty={(d) => d.length === 0}
        emptyRender={
          <EmptyState
            variant="cold"
            title="还没有止损止盈规则"
            description="为持仓配置止损/止盈后，scheduler 的 intraday_price_poll 任务会每 5 分钟检查并触发告警。"
            cta={{ label: '新增规则', onClick: handleCreate }}
          />
        }
      >
        {(data) => (
          <Table<HoldingRiskRule>
            rowKey="id"
            columns={columns}
            dataSource={data}
            loading={rulesQ.isFetching && !rulesQ.data}
            pagination={false}
            size="middle"
          />
        )}
      </QueryBoundary>
      <RiskRuleModal
        open={modalOpen}
        initial={editing}
        onCancel={() => setModalOpen(false)}
        onSave={handleSave}
      />
    </div>
  );
}
