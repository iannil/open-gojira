import { useState, useCallback } from 'react';
import {
  Badge,
  Button,
  Card,
  Col,
  DatePicker,
  Form,
  InputNumber,
  Modal,
  Row,
  Segmented,
  Space,
  Statistic,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  InfoCircleOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';

import { PageHeader, EmptyState } from '../../components/primitives';
import QueryBoundary from '../../components/QueryBoundary';
import { getAvailableQuantity, listDrafts, executeDraft, cancelDraft } from '../../api/client';
import type { DraftResponse } from '../../api/types';
import { useToastMutation } from '../../lib/useToastMutation';
import { draftKeys } from './queries';

const { Text, Paragraph } = Typography;

type TabValue = 'pending' | 'executed' | 'cancelled';

const TAB_OPTIONS = [
  { label: '待处理', value: 'pending' },
  { label: '已执行', value: 'executed' },
  { label: '已取消', value: 'cancelled' },
];

const SIDE_LABEL: Record<string, string> = { BUY: '买入', SELL: '卖出' };
const SIDE_COLOR: Record<string, string> = { BUY: 'green', SELL: 'red' };
const STATUS_LABEL: Record<string, string> = {
  pending: '待处理',
  executed: '已执行',
  cancelled: '已取消',
  superseded: '已取代',
};
const STATUS_COLOR: Record<string, string> = {
  pending: 'orange',
  executed: 'green',
  cancelled: 'default',
  superseded: 'default',
};
const TIER_LABEL: Record<string, string> = {
  aggressive: '积极',
  steady: '稳健',
};
const THESIS_LABEL: Record<string, string> = {
  healthy: '健康',
  invalidated: '证伪',
};
const SOURCE_LABEL: Record<string, string> = {
  evaluator: '规则引擎',
  quality_screen: '质量筛选',
  deep_research: '深度研究',
  thesis_tracker: '论点跟踪',
  theme_scan: '主题扫描',
  manual: '手动',
};

function formatDateTime(s: string | null): string {
  if (!s) return '—';
  return dayjs(s).format('MM-DD HH:mm');
}

/** Remaining time until expiration, as a human-readable string. */
function ttlLabel(expiresAt: string | null): { text: string; urgent: boolean } {
  if (!expiresAt) return { text: '—', urgent: false };
  const remaining = dayjs(expiresAt).diff(dayjs(), 'hour', true);
  if (remaining <= 0) return { text: '已过期', urgent: true };
  if (remaining < 24) return { text: `${Math.round(remaining)}h`, urgent: true };
  return { text: `${Math.round(remaining / 24)}d`, urgent: false };
}

// ── Execute Modal ──────────────────────────────────────────────────────

interface ExecuteModalProps {
  draft: DraftResponse;
  open: boolean;
  onClose: () => void;
}

function ExecuteModal({ draft, open, onClose }: ExecuteModalProps) {
  const [form] = Form.useForm();
  const executeM = useExecuteDraftMutation();

  const handleOk = useCallback(async () => {
    const values = await form.validateFields();
    executeM.mutate(
      {
        id: draft.id,
        payload: {
          price: values.price ?? undefined,
          quantity: values.quantity ?? undefined,
          filled_at: values.filled_at?.toISOString() ?? undefined,
        },
      },
      { onSuccess: () => { form.resetFields(); onClose(); } },
    );
  }, [draft.id, form, executeM, onClose]);

  return (
    <Modal
      title={`确认成交 — ${draft.code} ${SIDE_LABEL[draft.side]}`}
      open={open}
      onOk={handleOk}
      onCancel={onClose}
      confirmLoading={executeM.isPending}
      okText="确认成交"
      cancelText="取消"
    >
      <Paragraph type="secondary" style={{ marginBottom: 16 }}>
        在券商完成下单后，回填实际成交信息。价格和数量可偏离草案建议值。
      </Paragraph>
      <Form form={form} layout="vertical" initialValues={{ price: draft.target_price ?? undefined }}>
        <Form.Item name="price" label="实际成交价 (¥)" rules={[{ type: 'number', min: 0 }]}>
          <InputNumber style={{ width: '100%' }} precision={3} placeholder="可选，默认为空" />
        </Form.Item>
        <Form.Item name="quantity" label="实际成交数量" rules={[{ type: 'number', min: 1 }]}>
          <InputNumber style={{ width: '100%' }} placeholder={`建议: ${draft.suggested_quantity ?? '—'}`} />
        </Form.Item>
        <Form.Item name="filled_at" label="成交时间">
          <DatePicker showTime style={{ width: '100%' }} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

// ── T+1 Available Quantity Sub-component ──────────────────────────────

function SellAvailable({ code }: { code: string }) {
  const q = useQuery({
    queryKey: ['portfolio', code, 'available'],
    queryFn: () => getAvailableQuantity(code),
    staleTime: 10_000,
  });
  const data = q.data;
  if (!data) return <Text type="secondary">—</Text>;
  return (
    <Tooltip title={`总计 ${data.total} 股，T+1 冻结 ${data.frozen} 股`}>
      <Text type={data.available > 0 ? undefined : 'danger'}>
        可卖: <Text strong>{data.available}</Text> 股
      </Text>
    </Tooltip>
  );
}

// ── Draft Card ─────────────────────────────────────────────────────────

interface DraftCardProps {
  draft: DraftResponse;
  onExecute: (draft: DraftResponse) => void;
  onCancel: (id: number) => void;
  cancelPending: boolean;
}

function DraftCard({ draft, onExecute, onCancel, cancelPending }: DraftCardProps) {
  const ttl = ttlLabel(draft.expires_at);
  const isPending = draft.status === 'pending';

  return (
    <Card
      size="small"
      style={{ marginBottom: 12 }}
      styles={{
        header: {
          borderLeft: `4px solid ${draft.side === 'BUY' ? '#52c41a' : '#ff4d4f'}`,
        },
      }}
      title={
        <Space>
          <Text strong style={{ fontSize: 15 }}>{draft.code}</Text>
          <Tag color={SIDE_COLOR[draft.side]}>{SIDE_LABEL[draft.side]}</Tag>
          {draft.strategy_tier && (
            <Tag>{TIER_LABEL[draft.strategy_tier] ?? draft.strategy_tier}</Tag>
          )}
          {draft.thesis_status && (
            <Tag color={draft.thesis_status === 'healthy' ? 'green' : 'red'}>
              {THESIS_LABEL[draft.thesis_status]}
            </Tag>
          )}
          {isPending && ttl.urgent && <Badge count="即将过期" size="small" />}
        </Space>
      }
      extra={
        isPending ? (
          <Space>
            <Button type="primary" size="small" icon={<CheckCircleOutlined />} onClick={() => onExecute(draft)}>
              成交
            </Button>
            <Button size="small" danger loading={cancelPending} onClick={() => onCancel(draft.id)}>
              取消
            </Button>
          </Space>
        ) : (
          <Tag color={STATUS_COLOR[draft.status]}>{STATUS_LABEL[draft.status]}</Tag>
        )
      }
    >
      <Row gutter={[24, 8]}>
        {/* Reason & Source */}
        <Col xs={24}>
          <Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{draft.reason}</Paragraph>
        </Col>

        {/* Key metrics */}
        <Col xs={12} sm={6}>
          <Statistic
            title="来源"
            value={SOURCE_LABEL[draft.source] ?? draft.source}
            valueStyle={{ fontSize: 14 }}
          />
        </Col>
        <Col xs={12} sm={6}>
          <Statistic
            title="触发时间"
            value={formatDateTime(draft.triggered_at)}
            valueStyle={{ fontSize: 14 }}
          />
        </Col>
        <Col xs={12} sm={6}>
          <Statistic
            title="有效期"
            value={ttl.text}
            valueStyle={{ fontSize: 14, color: ttl.urgent ? '#ff4d4f' : undefined }}
            prefix={ttl.urgent ? <ClockCircleOutlined /> : undefined}
          />
        </Col>
        <Col xs={12} sm={6}>
          {draft.suggested_quantity != null && (
            <Statistic
              title="建议数量"
              value={draft.suggested_quantity}
              valueStyle={{ fontSize: 14 }}
              suffix="股"
            />
          )}
          {draft.suggested_quantity == null && draft.add_pct != null && (
            <Statistic
              title="建议加仓"
              value={draft.add_pct}
              valueStyle={{ fontSize: 14 }}
              suffix="%"
            />
          )}
          {draft.suggested_quantity == null && draft.reduce_pct_of_position != null && (
            <Statistic
              title="建议减仓"
              value={draft.reduce_pct_of_position}
              valueStyle={{ fontSize: 14 }}
              suffix="%"
            />
          )}
        </Col>

        {/* Phase 5 extras */}
        {draft.target_price != null && (
          <Col xs={12} sm={6}>
            <Statistic title="目标价" value={`¥${draft.target_price.toFixed(3)}`} valueStyle={{ fontSize: 14 }} />
          </Col>
        )}
        {draft.sizing_logic && (
          <Col xs={24}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              <InfoCircleOutlined /> 仓位逻辑：{draft.sizing_logic}
            </Text>
          </Col>
        )}

        {/* SELL: T+1 available */}
        {isPending && draft.side === 'SELL' && (
          <Col xs={24}>
            <SellAvailable code={draft.code} />
          </Col>
        )}
      </Row>
    </Card>
  );
}

// ── Mutations ──────────────────────────────────────────────────────────

function useExecuteDraftMutation() {
  return useToastMutation(
    (args: { id: number; payload: { price?: number; quantity?: number; filled_at?: string } }) =>
      executeDraft(args.id, args.payload),
    {
      successMsg: '已登记成交',
      invalidate: () => [draftKeys.all(), ['trades'], ['cockpit'], ['holdings']],
    },
  );
}

function useCancelDraftMutation() {
  return useToastMutation((id: number) => cancelDraft(id), {
    successMsg: '已取消草稿',
    invalidate: () => [draftKeys.all(), ['cockpit']],
  });
}

// ── Main Page ──────────────────────────────────────────────────────────

export default function DraftsPage() {
  const [tab, setTab] = useState<TabValue>('pending');
  const [executeTarget, setExecuteTarget] = useState<DraftResponse | null>(null);
  const [cancelId, setCancelId] = useState<number | null>(null);

  const draftsQ = useQuery({
    queryKey: draftKeys.list({ status: tab, limit: 200 }),
    queryFn: () => listDrafts({ status: tab, limit: 200 }),
    staleTime: 10_000,
  });

  const cancelM = useCancelDraftMutation();

  const allDrafts = draftsQ.data ?? [];

  const pendingCount = allDrafts.filter((d) => d.status === 'pending').length;
  const buyCount = allDrafts.filter((d) => d.side === 'BUY').length;
  const sellCount = allDrafts.filter((d) => d.side === 'SELL').length;

  const handleCancel = (id: number) => {
    setCancelId(id);
    cancelM.mutate(id, {
      onSettled: () => setCancelId(null),
    });
  };

  return (
    <div>
      <PageHeader
        title="交易草稿"
        purpose="应买 / 应卖 — 自动生成的交易建议，确认后记录为实际成交"
      />

      {/* Stats row */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={8}>
          <Card size="small">
            <Statistic title="待处理" value={pendingCount} prefix={<ThunderboltOutlined />} valueStyle={{ color: '#faad14' }} />
          </Card>
        </Col>
        <Col xs={8}>
          <Card size="small">
            <Statistic title="买入" value={buyCount} valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
        <Col xs={8}>
          <Card size="small">
            <Statistic title="卖出" value={sellCount} valueStyle={{ color: '#ff4d4f' }} />
          </Card>
        </Col>
      </Row>

      {/* Filter tabs */}
      <Segmented
        value={tab}
        onChange={(v) => setTab(v as TabValue)}
        options={TAB_OPTIONS}
        style={{ marginBottom: 16 }}
      />

      {/* Draft list */}
      <QueryBoundary
        query={draftsQ}
        isEmpty={(data) => data.length === 0}
        emptyRender={<EmptyState variant="quiet" title="暂无草稿" description="当前没有满足条件的交易建议。" />}
      >
        {(drafts) => (
          <div>
            {drafts.map((d) => (
              <DraftCard
                key={d.id}
                draft={d}
                onExecute={setExecuteTarget}
                onCancel={handleCancel}
                cancelPending={cancelId === d.id}
              />
            ))}
          </div>
        )}
      </QueryBoundary>

      {/* Execute modal */}
      {executeTarget && (
        <ExecuteModal
          draft={executeTarget}
          open={!!executeTarget}
          onClose={() => setExecuteTarget(null)}
        />
      )}
    </div>
  );
}
