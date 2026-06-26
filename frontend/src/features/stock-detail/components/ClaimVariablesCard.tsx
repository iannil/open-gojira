import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert, Button, Card, Empty, Popconfirm, Space, Tag, Typography, message,
} from 'antd';

import {
  approveClaimVariable,
  listClaimVariables,
  rejectClaimVariable,
} from '../../../api/research';
import type { ResearchClaimVariable } from '../../../api/types';
import EditClaimVariableModal from './EditClaimVariableModal';

const { Text } = Typography;

interface Props {
  stockCode: string;
}

const SOURCE_LABEL: Record<string, string> = {
  'financial:NIM': '净息差 (银行)',
  'financial:NPL': '不良贷款率 (银行)',
  'financial:revenue_growth': '营收同比',
  'financial:margin': '毛利率',
  'valuation:PE_percentile': 'PE 10y 分位',
  'valuation:PB_percentile': 'PB 10y 分位',
  'kline:price_drop_52w': '52 周跌幅',
};

function breachLabel(breachWhen: 'lt' | 'gt', threshold: number, unit: string | null): string {
  const op = breachWhen === 'lt' ? '<' : '>';
  return `${op} ${threshold}${unit || ''}`;
}

function VarRow({
  cv, onApprove, onReject, onEdit,
}: {
  cv: ResearchClaimVariable;
  onApprove: (id: number) => Promise<void>;
  onReject: (id: number) => Promise<void>;
  onEdit: (cv: ResearchClaimVariable) => void;
}) {
  return (
    <Card size="small" style={{ marginBottom: 'var(--sp-2)' }}>
      <Space direction="vertical" size="small" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text strong>{cv.variable_name}</Text>
          <Tag color="blue">{SOURCE_LABEL[cv.source] || cv.source}</Tag>
        </div>
        <Space size="middle">
          <Text type="secondary">
            告警阈值: <Text code>{breachLabel(cv.breach_when, cv.threshold_critical, cv.unit)}</Text>
          </Text>
          {cv.window_periods && cv.window_periods > 1 && (
            <Tag color="orange">连续 {cv.window_periods} 期</Tag>
          )}
          {cv.last_alerted_at && (
            <Tag color="red">最近告警 {new Date(cv.last_alerted_at).toLocaleDateString()}</Tag>
          )}
        </Space>
        {cv.review_note && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            备注: {cv.review_note}
          </Text>
        )}
        {cv.status === 'proposed' && (
          <Space>
            <Button type="primary" size="small" onClick={() => onApprove(cv.id)}>
              Approve
            </Button>
            <Button size="small" onClick={() => onEdit(cv)}>
              Edit
            </Button>
            <Popconfirm title="确认拒绝?" onConfirm={() => onReject(cv.id)}>
              <Button danger size="small">Reject</Button>
            </Popconfirm>
          </Space>
        )}
        {cv.status === 'active' && (
          <Space>
            <Tag color="green">监控中</Tag>
            <Button size="small" onClick={() => onEdit(cv)}>编辑阈值</Button>
            <Popconfirm title="确认停用?" onConfirm={() => onReject(cv.id)}>
              <Button danger size="small">停用</Button>
            </Popconfirm>
          </Space>
        )}
      </Space>
    </Card>
  );
}

export default function ClaimVariablesCard({ stockCode }: Props) {
  const queryClient = useQueryClient();
  const [editOpen, setEditOpen] = useState(false);
  const [editing, setEditing] = useState<ResearchClaimVariable | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['claim-variables', stockCode],
    queryFn: () => listClaimVariables(stockCode),
    refetchInterval: 30_000,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['claim-variables'] });

  const handleApprove = async (id: number) => {
    try {
      await approveClaimVariable(id, {});
      message.success('已激活监控');
      invalidate();
    } catch {
      message.error('激活失败');
    }
  };

  const handleReject = async (id: number) => {
    try {
      await rejectClaimVariable(id);
      message.success('已拒绝');
      invalidate();
    } catch {
      message.error('操作失败');
    }
  };

  const handleEdit = (cv: ResearchClaimVariable) => {
    setEditing(cv);
    setEditOpen(true);
  };

  const proposed = data?.proposed ?? [];
  const active = data?.active ?? [];
  const rejected = data?.rejected ?? [];

  return (
    <Card
      size="small"
      title={`论点变量提议 (待 review ${proposed.length} · 监控中 ${active.length})`}
      style={{ marginTop: 'var(--sp-3)' }}
    >
      {isLoading ? (
        <Text type="secondary">加载中...</Text>
      ) : (proposed.length === 0 && active.length === 0 && rejected.length === 0) ? (
        <Empty description="无 claim variable 提议 (serenity 跑完后会自动生成)" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <>
          {proposed.length > 0 && (
            <>
              <Alert type="warning" message={`待 review (${proposed.length})`} style={{ marginBottom: 'var(--sp-2)' }} />
              {proposed.map((cv) => (
                <VarRow key={cv.id} cv={cv} onApprove={handleApprove} onReject={handleReject} onEdit={handleEdit} />
              ))}
            </>
          )}
          {active.length > 0 && (
            <>
              <Alert type="success" message={`监控中 (${active.length})`} style={{ margin: 'var(--sp-2) 0' }} />
              {active.map((cv) => (
                <VarRow key={cv.id} cv={cv} onApprove={handleApprove} onReject={handleReject} onEdit={handleEdit} />
              ))}
            </>
          )}
          {rejected.length > 0 && (
            <>
              <Alert type="info" message={`已拒绝 (折叠, ${rejected.length})`} style={{ margin: 'var(--sp-2) 0' }} />
              {rejected.map((cv) => (
                <VarRow key={cv.id} cv={cv} onApprove={handleApprove} onReject={handleReject} onEdit={handleEdit} />
              ))}
            </>
          )}
        </>
      )}

      <EditClaimVariableModal
        open={editOpen}
        variable={editing}
        onClose={() => {
          setEditOpen(false);
          setEditing(null);
        }}
        onSaved={() => {
          invalidate();
          setEditOpen(false);
          setEditing(null);
        }}
      />
    </Card>
  );
}
