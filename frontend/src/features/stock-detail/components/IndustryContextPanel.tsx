import { useState, useEffect } from 'react';
import { Button, Descriptions, Select, Space, Tag, Tooltip, Typography } from 'antd';
import { EditOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';

import { listBusinessPatterns, updateStockBusinessPattern } from '../../../api/client';
import type { StockResponse } from '../../../api/types';
import { useToastMutation } from '../../../lib/useToastMutation';
import { stockKeys } from '../queries';

const TIER_COLOR: Record<number, string> = {
  0: 'red',
  1: 'default',
  2: 'blue',
  3: 'gold',
};
const TIER_LABEL: Record<number, string> = {
  0: '0 层选择权(被选择)',
  1: '1 层选择权(双向)',
  2: '2 层选择权(稀缺)',
  3: '3 层选择权(垄断)',
};

interface Props {
  stock: StockResponse;
  onUpdated?: () => void;
}

/**
 * Industry Context panel — shows the stock's BusinessPattern association.
 *
 * Design (T6.1):
 * - If business_pattern_id set: show pattern name, theme, first principle variable,
 *   power tier, thesis variables summary.
 * - If null: show prompt to associate (manual override via Select).
 * - Manual override sets inferred_at=NULL to mark user-driven (auto-inference skips).
 */
export default function IndustryContextPanel({ stock, onUpdated }: Props) {
  const [editing, setEditing] = useState(false);
  const [selectedPatternId, setSelectedPatternId] = useState<number | null>(
    stock.business_pattern_id ?? null,
  );

  useEffect(() => {
    setSelectedPatternId(stock.business_pattern_id ?? null);
  }, [stock.business_pattern_id]);

  const patternsQ = useQuery({
    queryKey: ['business-patterns'],
    queryFn: () => listBusinessPatterns(),
    staleTime: 60_000,
  });

  const updateM = useToastMutation(
    (patternId: number | null) =>
      updateStockBusinessPattern(stock.code, patternId),
    {
      successMsg: '商业模式已关联',
      errorMsg: '关联失败',
      invalidate: () => [stockKeys.detail(stock.code), ['business-patterns']],
      onSuccess: () => {
        setEditing(false);
        onUpdated?.();
      },
    },
  );

  const pattern = patternsQ.data?.find((p) => p.id === stock.business_pattern_id);
  const isManual = stock.business_pattern_inferred_at === null && stock.business_pattern_id !== null;

  if (editing) {
    return (
      <Descriptions column={1} size="small" title={null}>
        <Descriptions.Item label="关联商业模式">
          <Space>
            <Select
              style={{ minWidth: 240 }}
              allowClear
              showSearch
              placeholder="选择一个生意模式"
              value={selectedPatternId}
              onChange={(v) => setSelectedPatternId(v ?? null)}
              options={(patternsQ.data ?? []).map((p) => ({
                value: p.id,
                label: `${p.name}${p.first_principle_variable ? ` — ${p.first_principle_variable}` : ''}`,
              }))}
              optionFilterProp="label"
            />
            <Button
              type="primary"
              size="small"
              loading={updateM.isPending}
              onClick={() => updateM.mutate(selectedPatternId)}
            >
              保存
            </Button>
            <Button size="small" onClick={() => setEditing(false)}>
              取消
            </Button>
          </Space>
        </Descriptions.Item>
      </Descriptions>
    );
  }

  if (!pattern || stock.business_pattern_id == null) {
    return (
      <Descriptions column={1} size="small" title={null}>
        <Descriptions.Item label="商业模式">
          <Space>
            <Tag>未关联</Tag>
            <Tooltip title="自动推断返回 null(歧义或无匹配)。手动选择一个生意模式。">
              <Button size="small" icon={<EditOutlined />} onClick={() => setEditing(true)}>
                手动关联
              </Button>
            </Tooltip>
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label="Lixinger 行业">{stock.industry ?? '-'}</Descriptions.Item>
      </Descriptions>
    );
  }

  return (
    <Descriptions column={1} size="small" title={null}>
      <Descriptions.Item label="商业模式">
        <Space wrap>
          <Typography.Text strong>{pattern.name}</Typography.Text>
          <Tag color={TIER_COLOR[pattern.power_tier_baseline] ?? 'default'}>
            {TIER_LABEL[pattern.power_tier_baseline] ?? `${pattern.power_tier_baseline}`}
          </Tag>
          {isManual && (
            <Tooltip title="手动关联(自动推断不会覆盖)">
              <Tag color="purple">手动</Tag>
            </Tooltip>
          )}
          {!isManual && (
            <Tooltip title="自动推断自 Lixinger industry">
              <Tag>自动</Tag>
            </Tooltip>
          )}
          <Button size="small" icon={<EditOutlined />} onClick={() => setEditing(true)}>
            改
          </Button>
        </Space>
      </Descriptions.Item>
      {pattern.first_principle_variable && (
        <Descriptions.Item label="核心变量(第一性原理)">
          <Typography.Text style={{ color: 'var(--gojira-primary, #4F6D93)', fontWeight: 500 }}>
            {pattern.first_principle_variable}
          </Typography.Text>
        </Descriptions.Item>
      )}
      {pattern.description && (
        <Descriptions.Item label="说明">{pattern.description}</Descriptions.Item>
      )}
      {pattern.source_ref && (
        <Descriptions.Item label="文档">
          <Typography.Text type="secondary" style={{ fontSize: 'var(--fs-xs)' }}>
            📖 {pattern.source_ref}
          </Typography.Text>
        </Descriptions.Item>
      )}
      {(stock.thesis_variables?.length ?? 0) > 0 && (
        <Descriptions.Item label="论点变量">
          <Space size={4} wrap>
            {stock.thesis_variables!.map((v, i) => (
              <Tag key={i}>
                {v.name}
                {v.current_value != null && (
                  <span style={{ marginLeft: 4, opacity: 0.7 }}>
                    = {v.current_value}
                    {v.unit ? ` ${v.unit}` : ''}
                  </span>
                )}
              </Tag>
            ))}
          </Space>
        </Descriptions.Item>
      )}
    </Descriptions>
  );
}
