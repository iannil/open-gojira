import { useState } from "react";
import { Modal, Form, InputNumber, DatePicker, Input, Alert, Button } from "antd";
import dayjs from "dayjs";
import { createCashAdjustment } from "../api/client";
import { useAntdStatic } from "../hooks/useAntdStatic";

interface Props {
  open: boolean;
  /** "deposit" = 入金 (amount > 0); "withdrawal" = 取现 (auto negate) */
  mode: "deposit" | "withdrawal";
  onClose: () => void;
  onCreated?: () => void;
}

export function CashAdjustmentModal({ open, mode, onClose, onCreated }: Props) {
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { message } = useAntdStatic();

  const isDeposit = mode === "deposit";
  const title = isDeposit ? "入金" : "取现";

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      setError(null);
      const amount = isDeposit
        ? Math.abs(values.amount)
        : -Math.abs(values.amount);
      await createCashAdjustment({
        amount,
        happened_at: values.happened_at.toISOString(),
        reason: isDeposit ? "deposit" : "withdrawal",
        note: values.note,
      });
      message.success(`${title} ¥${Math.abs(values.amount).toFixed(2)} 已记录`);
      form.resetFields();
      onCreated?.();
      onClose();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(
        typeof detail === "string"
          ? detail
          : err?.message || "提交失败",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={title}
      open={open}
      onCancel={onClose}
      footer={[
        <Button key="cancel" onClick={onClose}>
          取消
        </Button>,
        <Button
          key="submit"
          type="primary"
          loading={submitting}
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
          showIcon
        />
      )}
      <Form
        form={form}
        layout="vertical"
        initialValues={{ happened_at: dayjs() }}
      >
        <Form.Item
          name="amount"
          label="金额(¥)"
          rules={[
            { required: true, message: "必填" },
            { type: "number", min: 0.01, message: "必须 > 0" },
          ]}
        >
          <InputNumber
            style={{ width: "100%" }}
            step={10000}
            min={0.01}
            formatter={(v) => `¥ ${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}
            parser={(v) =>
              (Number(v?.replace(/¥\s?|,/g, "") || 0) as unknown) as 0.01
            }
          />
        </Form.Item>
        <Form.Item
          name="happened_at"
          label="发生时间"
          rules={[{ required: true }]}
        >
          <DatePicker showTime format="YYYY-MM-DD HH:mm" />
        </Form.Item>
        <Form.Item name="note" label="备注">
          <Input.TextArea rows={2} placeholder="例:月度入金 / 应急取现" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
