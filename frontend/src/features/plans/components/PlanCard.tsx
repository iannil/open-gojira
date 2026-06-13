import { Button, Card, Popconfirm, Space, Tag, Typography } from 'antd';
import { PlayCircleOutlined } from '@ant-design/icons';
import type { PlanResponse, StrategyResponse } from '../../../api/types';

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  active: { color: 'green', label: '运行中' },
  paused: { color: 'orange', label: '已暂停' },
  archived: { color: 'default', label: '已归档' },
};

const LOGIC_MAP: Record<string, string> = { AND: '全部满足', OR: '任一满足' };

const SCOPE_MAP: Record<string, string> = {
  all_stocks: '全市场',
  industries: '指定行业',
  index: '指数成分',
  watchlist: '自选股',
  custom: '自定义列表',
};

export interface PlanCardProps {
  plan: PlanResponse;
  strategies: StrategyResponse[];
  onRun: () => void;
  onToggle: () => void;
  onDelete: () => void;
}

export default function PlanCard({
  plan: p,
  strategies,
  onRun,
  onToggle,
  onDelete,
}: PlanCardProps) {
  const strategyName = (id: number) =>
    strategies.find((s) => s.id === id)?.name ?? `#${id}`;

  return (
    <Card
      title={
        <Space>
          <span>{p.name}</span>
          <Tag color={STATUS_MAP[p.status]?.color}>{STATUS_MAP[p.status]?.label}</Tag>
          {p.is_builtin && <Tag color="gold">内置</Tag>}
        </Space>
      }
      extra={
        <Space>
          <Button size="small" icon={<PlayCircleOutlined />} onClick={onRun}>
            运行
          </Button>
          {!p.is_builtin && (
            <Popconfirm title="确定删除？" onConfirm={onDelete}>
              <Button size="small" danger>删除</Button>
            </Popconfirm>
          )}
        </Space>
      }
    >
      <div style={{ marginBottom: 8 }}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {p.description}
        </Typography.Text>
      </div>
      <div style={{ marginBottom: 8 }}>
        <Tag color={p.strategy_composition.logic === 'AND' ? 'blue' : 'orange'}>
          {LOGIC_MAP[p.strategy_composition.logic] ?? p.strategy_composition.logic}
        </Tag>
        {p.strategy_composition.strategy_ids.map((id) => (
          <Tag key={id}>{strategyName(id)}</Tag>
        ))}
      </div>
      <Space size="small" style={{ fontSize: 12 }}>
        <span>范围: {SCOPE_MAP[p.scan_scope.type] ?? p.scan_scope.type}</span>
        {p.trading_rules && <Tag color="purple">有交易规则</Tag>}
        <span>候选: {p.candidate_count}</span>
      </Space>
      <div style={{ marginTop: 8 }}>
        <Button size="small" onClick={onToggle}>
          {p.status === 'active' ? '暂停' : '启用'}
        </Button>
      </div>
    </Card>
  );
}
