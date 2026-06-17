import { useState } from 'react';
import { Modal, Checkbox, Tag, Typography, InputNumber, Form, Space } from 'antd';

interface AutoCheckResult {
  in_plan: boolean;
  position_ok: boolean;
  is_production_asset: boolean;
  high_dyr_baseline: boolean;
}

export interface BrokerFill {
  price: number;
  quantity: number;
}

interface Props {
  open: boolean;
  side: 'BUY' | 'SELL';
  stockCode: string;
  theme: string | null;
  tier: string | null;
  autoChecks?: Partial<AutoCheckResult>;
  suggestedQuantity?: number | null;
  onConfirm: (checklist: Record<string, boolean>, fill: BrokerFill) => void;
  onCancel: () => void;
}

const AUTO_ITEMS = [
  { key: 'in_plan', label: '此交易在预定义预案中' },
  { key: 'position_ok', label: '仓位在限制范围内' },
  { key: 'is_production_asset', label: '买入的是生产资料（有 tier 分层）' },
  { key: 'high_dyr_baseline', label: '股息率满足安全底线' },
];

const MANUAL_ITEMS = [
  { key: 'no_borrow', label: '本仓使用自有资金 (非融资融券 / 信用卡 / 亲友借款) — invest2 §4' },
  { key: 'not_emotion', label: '非因恐惧卖出/因贪婪买入' },
  { key: 'read_report', label: '已阅读最新财报' },
  { key: 'stay_boundary', label: '坚守能力圈，不追热点' },
  { key: 'reverse_thinking', label: '逆向思考：敢于低位买、高位卖' },
  { key: 'slow_is_fast', label: '慢即是快：追求长期复利而非短期暴利' },
  // ── M1 (Batch 5 2026-06-17): invest1 第13章 "人之道" 加减仓纪律 ──
  { key: 'm1a_no_dip_buy', label: '本股跌幅 < 10% 时未补仓 (invest1 §13 "拉开价格梯度")' },
  { key: 'm1b_no_loss_avg', label: '本股不在亏损中加仓 (反 "回本强迫症", invest1 §13)' },
  { key: 'm1c_winner_add', label: '盈利股已加仓或在加仓计划中 (invest1 §13 "加仓赢家")' },
  // ── M3 (Batch 5 2026-06-17): invest1 第12章 "破除三大妄念" ──
  { key: 'm3d_no_loss_aversion', label: '未因亏损就死守不卖 (反损失厌恶, invest1 §12)' },
  { key: 'm3e_no_anchor', label: '未以历史最高/最低价为决策锚 (反锚定效应, invest1 §12)' },
];

export default function DisciplineChecklistModal({
  open,
  side,
  stockCode,
  theme,
  tier,
  autoChecks,
  suggestedQuantity,
  onConfirm,
  onCancel,
}: Props) {
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [price, setPrice] = useState<number | null>(null);
  const [quantity, setQuantity] = useState<number | null>(suggestedQuantity ?? null);

  const allChecked = [...AUTO_ITEMS, ...MANUAL_ITEMS].every(
    (item) => checked[item.key]
  );
  const fillValid = price !== null && price > 0 && quantity !== null && quantity > 0;

  const handleToggle = (key: string) => {
    setChecked((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleConfirm = () => {
    if (!fillValid) return;
    onConfirm(checked, { price: price!, quantity: quantity! });
  };

  const tierLabel = tier === 'core' ? '核心' : tier === 'satellite' ? '卫星' : null;

  return (
    <Modal
      title={`交易前纪律检查 — ${side === 'BUY' ? '买入' : '卖出'} ${stockCode}`}
      open={open}
      onOk={handleConfirm}
      onCancel={onCancel}
      okText="确认执行"
      okButtonProps={{ disabled: !allChecked || !fillValid }}
      width={520}
    >
      <Typography.Paragraph type="secondary" style={{ marginBottom: 16 }}>
        重审 #2 + #7B: 成交回报 + invest3 核心十诫,一屏完成。
      </Typography.Paragraph>

      {/* Section 1: broker fill (重审 #2 — merged trade entry) */}
      <div style={{ marginBottom: 16, padding: 12, background: 'var(--bg-secondary, #fafafa)', borderRadius: 8 }}>
        <Typography.Text strong>成交回报 (broker fill)</Typography.Text>
        <Form layout="vertical" style={{ marginTop: 8 }}>
          <Space.Compact style={{ width: '100%' }}>
            <Form.Item label="实际成交价" style={{ flex: 1, marginRight: 8, marginBottom: 0 }}>
              <InputNumber
                value={price ?? undefined}
                onChange={v => setPrice(v ?? null)}
                min={0}
                step={0.01}
                placeholder="如 100.50"
                style={{ width: '100%' }}
                addonAfter="元"
              />
            </Form.Item>
            <Form.Item label="成交数量" style={{ flex: 1, marginBottom: 0 }}>
              <InputNumber
                value={quantity ?? undefined}
                onChange={v => setQuantity(v ?? null)}
                min={100}
                step={100}
                placeholder={suggestedQuantity ? String(suggestedQuantity) : '如 1000'}
                style={{ width: '100%' }}
                addonAfter="股"
              />
            </Form.Item>
          </Space.Compact>
        </Form>
      </div>

      {/* Section 2: auto checklist */}
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

      {/* Section 3: manual checklist */}
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

      {(!allChecked || !fillValid) && (
        <div style={{ marginTop: 12, color: '#D97706', fontSize: 12 }}>
          {!fillValid && '请填写成交回报 (价格 + 数量); '}
          {!allChecked && '请确认所有检查项'}
        </div>
      )}
    </Modal>
  );
}
