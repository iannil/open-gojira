import { useState } from 'react';
import { Modal, Form, Input, InputNumber, Select, DatePicker, Button, Alert } from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { createTrade, getPriceBand } from '../api/client';
import { useAntdStatic } from '../hooks/useAntdStatic';
import type { PriceBand, Trade, TradeSide } from '../api/types';

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated?: (trade: Trade) => void;
}

interface FormValues {
  stock_code: string;
  side: TradeSide;
  price: number;
  quantity: number;
  filled_at: Dayjs;
  commission_override?: number;
  note?: string;
}

// Display name + applicable limit percent by board (for warning copy).
function boardLimitPct(band: PriceBand): string {
  if (band.is_st) return '±5%';
  switch (band.board) {
    case 'bjse':
      return '±30%';
    case 'chinext':
    case 'star':
      return '±20%';
    default:
      return '±10%';
  }
}

export default function TradeEntryModal({ open, onClose, onCreated }: Props) {
  const [form] = Form.useForm<FormValues>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [priceBand, setPriceBand] = useState<PriceBand | null>(null);
  const [priceWarning, setPriceWarning] = useState<string | null>(null);
  const { message } = useAntdStatic();

  const handleCodeChange = async (rawCode: string) => {
    const code = rawCode.trim();
    setPriceBand(null);
    setPriceWarning(null);
    if (code.length < 6) return;
    try {
      const band = await getPriceBand(code);
      setPriceBand(band);
      if (band.is_suspended) {
        setPriceWarning(
          `该股已停牌(status=${band.listing_status ?? 'unknown'}),不可交易`,
        );
      }
    } catch {
      // Stock not found or network error: stay quiet — let backend validate on submit.
    }
  };

  const handlePriceChange = (value: number | null) => {
    if (value == null || !priceBand || priceBand.low == null || priceBand.high == null) {
      setPriceWarning(null);
      return;
    }
    const low = priceBand.low;
    const high = priceBand.high;
    // Tolerance 0.01 to mirror backend.
    if (value < low - 0.01 || value > high + 0.01) {
      setPriceWarning(
        `价格 ¥${value.toFixed(2)} 超出今日涨跌停区间 [¥${low.toFixed(2)}, ¥${high.toFixed(2)}](${boardLimitPct(priceBand)})`,
      );
    } else {
      setPriceWarning(null);
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (priceBand?.is_suspended) {
        setError(`该股已停牌(status=${priceBand.listing_status ?? 'unknown'}),不可交易`);
        return;
      }
      setSubmitting(true);
      setError(null);
      const trade = await createTrade({
        stock_code: values.stock_code.trim(),
        side: values.side,
        price: values.price,
        quantity: values.quantity,
        filled_at: values.filled_at.toISOString(),
        source: 'manual',
        commission_override: values.commission_override,
        note: values.note?.trim() || undefined,
      });
      message.success(`成交已录入 #${trade.id}`);
      form.resetFields();
      setPriceBand(null);
      setPriceWarning(null);
      onCreated?.(trade);
      onClose();
    } catch (err) {
      if (err && typeof err === 'object' && 'errorFields' in err) {
        // antd Form.validateFields rejection — do not show banner
        return;
      }
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || (err as Error)?.message || '录入失败');
    } finally {
      setSubmitting(false);
    }
  };

  const suspended = priceBand?.is_suspended === true;
  const submitDisabled = suspended;

  return (
    <Modal
      title="录入成交"
      open={open}
      onCancel={onClose}
      destroyOnHidden
      footer={[
        <Button key="cancel" onClick={onClose}>
          取消
        </Button>,
        <Button
          key="submit"
          type="primary"
          loading={submitting}
          disabled={submitDisabled}
          onClick={handleSubmit}
        >
          提交
        </Button>,
      ]}
    >
      {error && (
        <Alert
          type="error"
          message={error}
          style={{ marginBottom: 16 }}
          closable
          onClose={() => setError(null)}
        />
      )}
      <Form
        form={form}
        layout="vertical"
        initialValues={{ side: 'BUY' as TradeSide, filled_at: dayjs() }}
      >
        <Form.Item
          name="stock_code"
          label="股票代码"
          rules={[{ required: true, message: '必填' }]}
        >
          <Input
            placeholder="例如 600519"
            autoComplete="off"
            onChange={(e) => void handleCodeChange(e.target.value)}
          />
        </Form.Item>
        <Form.Item name="side" label="方向" rules={[{ required: true }]}>
          <Select
            options={[
              { value: 'BUY', label: '买入' },
              { value: 'SELL', label: '卖出' },
              { value: 'DIVIDEND', label: '分红(现金)' },
              { value: 'CORP_ACTION', label: '公司行为' },
            ]}
          />
        </Form.Item>
        <Form.Item
          name="price"
          label="成交价"
          rules={[
            { required: true, message: '必填' },
            { type: 'number', min: 0.0001, message: '必须为正数' },
          ]}
          extra={
            priceBand && priceBand.low != null && priceBand.high != null
              ? `今日涨跌停 [¥${priceBand.low.toFixed(2)}, ¥${priceBand.high.toFixed(2)}](${boardLimitPct(priceBand)})`
              : undefined
          }
        >
          <InputNumber
            style={{ width: '100%' }}
            step={0.01}
            precision={3}
            onChange={(v) => handlePriceChange(v as number | null)}
          />
        </Form.Item>
        {priceWarning && (
          <Alert
            type={suspended ? 'error' : 'warning'}
            message={priceWarning}
            style={{ marginBottom: 16 }}
            showIcon
          />
        )}
        <Form.Item
          name="quantity"
          label="数量(股)"
          rules={[
            { required: true, message: '必填' },
            { type: 'number', min: 1, message: '至少 1 股' },
          ]}
        >
          <InputNumber style={{ width: '100%' }} step={100} precision={0} />
        </Form.Item>
        <Form.Item
          name="filled_at"
          label="成交时间"
          rules={[{ required: true, message: '必填' }]}
        >
          <DatePicker showTime format="YYYY-MM-DD HH:mm" style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item
          name="commission_override"
          label="佣金覆盖(可选)"
          tooltip="留空由系统按券商费率自动计算"
        >
          <InputNumber
            style={{ width: '100%' }}
            step={0.01}
            precision={2}
            min={0}
            placeholder="留空自动算"
          />
        </Form.Item>
        <Form.Item name="note" label="备注">
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
