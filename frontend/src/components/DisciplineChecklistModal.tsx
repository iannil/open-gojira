import { useState } from 'react';
import { Modal, Checkbox, Tag, Typography } from 'antd';

interface AutoCheckResult {
  in_plan: boolean;
  position_ok: boolean;
  is_production_asset: boolean;
  high_dyr_baseline: boolean;
}

interface Props {
  open: boolean;
  side: 'BUY' | 'SELL';
  stockCode: string;
  theme: string | null;
  tier: string | null;
  autoChecks?: Partial<AutoCheckResult>;
  onConfirm: (checklist: Record<string, boolean>) => void;
  onCancel: () => void;
}

const AUTO_ITEMS = [
  { key: 'in_plan', label: '此交易在预定义预案中' },
  { key: 'position_ok', label: '仓位在限制范围内' },
  { key: 'is_production_asset', label: '买入的是生产资料（有 tier 分层）' },
  { key: 'high_dyr_baseline', label: '股息率满足安全底线' },
];

const MANUAL_ITEMS = [
  { key: 'no_borrow', label: '未使用借来的资金' },
  { key: 'not_emotion', label: '非因恐惧卖出/因贪婪买入' },
  { key: 'read_report', label: '已阅读最新财报' },
  { key: 'stay_boundary', label: '坚守能力圈，不追热点' },
  { key: 'reverse_thinking', label: '逆向思考：敢于低位买、高位卖' },
  { key: 'slow_is_fast', label: '慢即是快：追求长期复利而非短期暴利' },
];

export default function DisciplineChecklistModal({
  open,
  side,
  stockCode,
  theme,
  tier,
  autoChecks,
  onConfirm,
  onCancel,
}: Props) {
  const [checked, setChecked] = useState<Record<string, boolean>>({});

  const allChecked = [...AUTO_ITEMS, ...MANUAL_ITEMS].every(
    (item) => checked[item.key]
  );

  const handleToggle = (key: string) => {
    setChecked((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleConfirm = () => {
    onConfirm(checked);
  };

  const tierLabel = tier === 'core' ? '核心' : tier === 'watch' ? '关注' : null;

  return (
    <Modal
      title={`交易前纪律检查 — ${side === 'BUY' ? '买入' : '卖出'} ${stockCode}`}
      open={open}
      onOk={handleConfirm}
      onCancel={onCancel}
      okText="确认执行"
      okButtonProps={{ disabled: !allChecked }}
      width={520}
    >
      <Typography.Paragraph type="secondary" style={{ marginBottom: 16 }}>
        执行前请逐项确认（invest3 核心十诫）
      </Typography.Paragraph>

      <div style={{ marginBottom: 12 }}>
        <Typography.Text strong>自动验证</Typography.Text>
        <div style={{ marginTop: 8 }}>
          {AUTO_ITEMS.map((item) => {
            const result = autoChecks?.[item.key as keyof AutoCheckResult];
            const autoPass = result === true;
            return (
              <div key={item.key} style={{ marginBottom: 6 }}>
                <Checkbox
                  checked={checked[item.key]}
                  onChange={() => handleToggle(item.key)}
                >
                  {item.label}
                  {autoPass ? (
                    <Tag color="green" style={{ marginLeft: 6 }}>通过</Tag>
                  ) : result === false ? (
                    <Tag color="orange" style={{ marginLeft: 6 }}>未通过</Tag>
                  ) : (
                    <Tag style={{ marginLeft: 6 }}>需确认</Tag>
                  )}
                </Checkbox>
                {item.key === 'is_production_asset' && tierLabel && (
                  <span style={{ color: '#4F6D93', marginLeft: 4 }}>({tierLabel})</span>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div>
        <Typography.Text strong>心理确认</Typography.Text>
        <div style={{ marginTop: 8 }}>
          {MANUAL_ITEMS.map((item) => (
            <div key={item.key} style={{ marginBottom: 6 }}>
              <Checkbox checked={checked[item.key]} onChange={() => handleToggle(item.key)}>
                {item.label}
                {item.key === 'stay_boundary' && theme && (
                  <span style={{ color: '#4F6D93', marginLeft: 4 }}>({theme})</span>
                )}
              </Checkbox>
            </div>
          ))}
        </div>
      </div>

      {!allChecked && (
        <div style={{ marginTop: 12, color: '#D97706', fontSize: 12 }}>
          请确认所有检查项后执行
        </div>
      )}
    </Modal>
  );
}
