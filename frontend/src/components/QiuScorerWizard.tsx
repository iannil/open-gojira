import { useState } from 'react';
import { Modal, Radio, Typography, Space, Divider } from 'antd';
import { updateQiuScore } from '../api/client';

interface Props {
  open: boolean;
  code: string;
  onClose: () => void;
  onSaved: () => void;
  initialValues?: {
    upstream_power?: number;
    downstream_power?: number;
    government_power?: number;
  };
}

const DIMENSIONS = [
  {
    key: 'upstream_power' as const,
    label: '上游选择权',
    question: '供应商能否挤压利润？',
    hint: '原材料是否集中、替代品是否稀缺',
  },
  {
    key: 'downstream_power' as const,
    label: '下游选择权',
    question: '客户能否挤压利润？',
    hint: '产品是否可替代、客户是否集中',
  },
  {
    key: 'government_power' as const,
    label: '政府选择权',
    question: '监管能否摧毁商业模式？',
    hint: '行业是否强监管、政策是否频变',
  },
];

export default function QiuScorerWizard({ open, code, onClose, onSaved, initialValues }: Props) {
  const [scores, setScores] = useState({
    upstream_power: initialValues?.upstream_power ?? 0,
    downstream_power: initialValues?.downstream_power ?? 0,
    government_power: initialValues?.government_power ?? 0,
  });
  const [saving, setSaving] = useState(false);

  const total = scores.upstream_power + scores.downstream_power + scores.government_power;

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateQiuScore(code, {
        upstream_power: scores.upstream_power,
        downstream_power: scores.downstream_power,
        government_power: scores.government_power,
        evidence: {},
      });
      onSaved();
      onClose();
    } catch {
      // error handled by caller
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={`选择权评分 — ${code}`}
      open={open}
      onOk={handleSave}
      onCancel={onClose}
      confirmLoading={saving}
      okText="保存评分"
      width={520}
    >
      <div style={{ marginBottom: 16 }}>
        <Typography.Text type="secondary">
          选择权理论：评估对上游/下游/政府的选择权位阶 (invest1 §二)
        </Typography.Text>
      </div>

      {DIMENSIONS.map((dim) => (
        <div key={dim.key} style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>{dim.label}</div>
          <div style={{ fontSize: 12, color: '#78716C', marginBottom: 8 }}>
            {dim.question}（{dim.hint}）
          </div>
          <Radio.Group
            value={scores[dim.key]}
            onChange={(e) => setScores({ ...scores, [dim.key]: e.target.value })}
          >
            <Radio.Button value={0}>0 被单向选择</Radio.Button>
            <Radio.Button value={1}>1 双向选择权</Radio.Button>
          </Radio.Group>
        </div>
      ))}

      <Divider />

      <div style={{ textAlign: 'center' }}>
        <Space>
          <span style={{ fontSize: 14, color: '#57534E' }}>总分</span>
          <span
            style={{
              fontSize: 28,
              fontWeight: 700,
              color: total >= 2 ? '#16A34A' : total >= 1 ? '#D97706' : '#DC2626',
            }}
          >
            {total}
          </span>
          <span style={{ fontSize: 14, color: '#78716C' }}>/ 3</span>
        </Space>
        <div style={{ fontSize: 12, color: '#78716C', marginTop: 4 }}>
          {total >= 3
            ? '三求全胜 — 极强商业模式'
            : total >= 2
              ? '两求占优 — 较强护城河'
              : total >= 1
                ? '一求勉强 — 需警惕'
                : '零求皆弱 — 高风险'}
        </div>
      </div>
    </Modal>
  );
}
