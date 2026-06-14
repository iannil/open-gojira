import { Descriptions, Space, Switch, Tag, Tooltip, Typography } from 'antd';

import { updateStockResourceFlags } from '../../../api/client';
import type { ResourceFlagsUpdate, StockResponse } from '../../../api/types';
import { useToastMutation } from '../../../lib/useToastMutation';
import { stockKeys } from '../queries';

interface Props {
  stock: StockResponse;
}

/**
 * Resource Flags panel — G2/G4 manual overrides + G3 forward DYR display.
 *
 * G2 (invest3 §13): is_cost_leader — only meaningful for midstream patterns
 * (煤化工/电解铝). When null, plan_runner treats as non-leader → 剔除.
 *
 * G4 (invest3 §12): has_mine + domestic_leader — resource_hard_asset strategy
 * requires both True. Null = inconclusive → 剔除.
 *
 * G3 (invest3 §8): forward_dyr is computed backend-side (3-year avg per-share
 * / latest close). Display only — no manual override (algorithm-driven).
 */
export default function ResourceFlagsPanel({ stock }: Props) {
  const flagsM = useToastMutation(
    (flags: ResourceFlagsUpdate) =>
      updateStockResourceFlags(stock.code, flags),
    {
      successMsg: '资源股属性已更新',
      errorMsg: '更新失败',
      invalidate: () => [stockKeys.detail(stock.code)],
    },
  );

  const pct = (v: number | null | undefined): string =>
    v == null ? '—' : `${(v * 100).toFixed(2)}%`;

  return (
    <Descriptions column={1} size="small" title={null}>
      <Descriptions.Item label="预期股息率 (forward DYR)">
        <Space>
          <Typography.Text strong style={{ color: 'var(--gojira-primary, #4F6D93)' }}>
            {pct(stock.forward_dyr)}
          </Typography.Text>
          <Tooltip title="G3: 3 年平均每股分红 / 最新收盘价。Null = 数据不足(无分红历史或停牌)。文档 §8 反复强调'预期股息率，而不是过去股息率'。">
            <Tag color={stock.forward_dyr == null ? 'orange' : 'blue'} style={{ cursor: 'help' }}>
              {stock.forward_dyr == null ? '数据不足' : 'G3'}
            </Tag>
          </Tooltip>
        </Space>
      </Descriptions.Item>

      <Descriptions.Item label="成本领先 (G2)">
        <Space>
          <Switch
            size="small"
            checked={stock.is_cost_leader === true}
            onChange={(checked) =>
              flagsM.mutate({ cost_leader: checked })
            }
          />
          <Tooltip title="G2 (invest3 §13): 仅对中游 pattern(煤化工/电解铝)有意义。True = 该股在 pattern 内是成本领先者。Null = 未判定 → plan_runner 视为非 leader → 剔除。">
            <Tag style={{ cursor: 'help' }}>
              {stock.is_cost_leader == null ? '未判定' : stock.is_cost_leader ? '是' : '否'}
            </Tag>
          </Tooltip>
        </Space>
      </Descriptions.Item>

      <Descriptions.Item label="有矿 (G4)">
        <Space>
          <Switch
            size="small"
            checked={stock.has_mine === true}
            onChange={(checked) => flagsM.mutate({ has_mine: checked })}
          />
          <Tooltip title="G4 (invest3 §12): True = 该股拥有自有矿产资源(不是纯加工中游)。resource_hard_asset 策略要求 == True。">
            <Tag style={{ cursor: 'help' }}>
              {stock.has_mine == null ? '未判定' : stock.has_mine ? '是' : '否'}
            </Tag>
          </Tooltip>
        </Space>
      </Descriptions.Item>

      <Descriptions.Item label="国内领先 (G4)">
        <Space>
          <Switch
            size="small"
            checked={stock.domestic_leader === true}
            onChange={(checked) => flagsM.mutate({ domestic_leader: checked })}
          />
          <Tooltip title="G4 (invest3 §12): True = 该股在国内资源板块处于领先地位(国内优先于海外)。resource_hard_asset 策略要求 == True。">
            <Tag style={{ cursor: 'help' }}>
              {stock.domestic_leader == null ? '未判定' : stock.domestic_leader ? '是' : '否'}
            </Tag>
          </Tooltip>
        </Space>
      </Descriptions.Item>

      <Descriptions.Item label="扩产可见 (B2)">
        <Space>
          <Switch
            size="small"
            checked={stock.expansion_outlook === true}
            onChange={(checked) => flagsM.mutate({ expansion_outlook: checked })}
          />
          <Tooltip title="B2 (invest3 §12 资源股 7 维): True = 该股有明确扩产计划/在建产能。主观判断,人工标注。resource_hard_asset 策略要求 == True。">
            <Tag style={{ cursor: 'help' }}>
              {stock.expansion_outlook == null ? '未判定' : stock.expansion_outlook ? '是' : '否'}
            </Tag>
          </Tooltip>
        </Space>
      </Descriptions.Item>

      <Descriptions.Item label="地缘稳定 (B2)">
        <Space>
          <Switch
            size="small"
            checked={stock.geo_risk === true}
            onChange={(checked) => flagsM.mutate({ geo_risk: checked })}
          />
          <Tooltip title="B2 (invest3 §12 资源股 7 维): True = 该股地缘税收风险可接受(国内或稳定海外)。False = 高风险(战乱/制裁/税收突变)。resource_hard_asset 策略要求 == True。">
            <Tag style={{ cursor: 'help' }}>
              {stock.geo_risk == null ? '未判定' : stock.geo_risk ? '是' : '否'}
            </Tag>
          </Tooltip>
        </Space>
      </Descriptions.Item>
    </Descriptions>
  );
}
