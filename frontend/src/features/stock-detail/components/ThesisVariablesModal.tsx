import { useEffect, useState } from 'react';
import {
  Button,
  Card,
  Empty,
  Input,
  InputNumber,
  Modal,
  Space,
} from 'antd';
import type { ThesisVariable } from '../../../api/types';
import { fetchThesisTemplates } from '../../../api/client';
import { useAntdStatic } from '../../../hooks/useAntdStatic';

interface Props {
  open: boolean;
  code: string;
  initial: ThesisVariable[];
  saving: boolean;
  onCancel: () => void;
  onSave: (vars: ThesisVariable[]) => Promise<void>;
}

export default function ThesisVariablesModal({
  open,
  code,
  initial,
  saving,
  onCancel,
  onSave,
}: Props) {
  const { message } = useAntdStatic();
  const [vars, setVars] = useState<ThesisVariable[]>(initial);

  useEffect(() => {
    if (open) setVars(initial);
  }, [open, initial]);

  const handleAdd = () => {
    setVars((prev) => [
      ...prev,
      {
        name: '',
        current_value: null,
        target_condition: null,
        unit: null,
        source: '',
      },
    ]);
  };

  const handleRemove = (index: number) => {
    setVars((prev) => prev.filter((_, i) => i !== index));
  };

  const handleChange = (
    index: number,
    field: keyof ThesisVariable,
    value: string | number | null,
  ) => {
    setVars((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], [field]: value };
      return next;
    });
  };

  const handleLoadTemplates = async () => {
    try {
      const res = await fetchThesisTemplates(code);
      if (res.templates.length === 0) {
        // After T6.1, templates come from BusinessPattern, not industry string.
        // Empty templates usually means stock has no business_pattern_id.
        message.info(
          res.industry
            ? `"${res.industry}" 暂无模板。若未关联商业模式,请先在「Industry Context」面板关联。`
            : '该股票尚未关联商业模式,请先在「Industry Context」面板关联一个生意模式。',
        );
        return;
      }
      const newVars: ThesisVariable[] = res.templates.map((t) => ({
        name: t.name,
        current_value: null,
        target_condition: null,
        unit: t.unit,
        source: t.source,
      }));
      setVars((prev) => [...prev, ...newVars]);
      message.success(`已加载 ${newVars.length} 个模板变量`);
    } catch {
      message.error('加载模板失败');
    }
  };

  const handleOk = async () => {
    const valid = vars.every((v) => v.name && v.source);
    if (!valid) {
      message.error('请填写完整的变量名称和数据来源');
      return;
    }
    await onSave(vars);
  };

  return (
    <Modal
      open={open}
      title="编辑变量"
      okText="保存"
      cancelText="取消"
      onCancel={onCancel}
      onOk={handleOk}
      confirmLoading={saving}
      width={800}
      destroyOnHidden
    >
      <div style={{ marginBottom: 'var(--sp-4)' }}>
        <Space>
          <Button size="small" onClick={handleAdd}>
            添加变量
          </Button>
          <Button size="small" onClick={handleLoadTemplates}>
            从行业模板加载
          </Button>
        </Space>
      </div>
      {vars.length === 0 ? (
        <Empty
          description="暂无变量，点击上方按钮添加"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      ) : (
        <Space direction="vertical" style={{ width: '100%' }} size={16}>
          {vars.map((variable, index) => (
            <Card
              key={index}
              className="gojira-card"
              bordered={false}
              size="small"
              title={`变量 ${index + 1}`}
              extra={
                <Button
                  size="small"
                  danger
                  onClick={() => handleRemove(index)}
                >
                  删除
                </Button>
              }
            >
              <Space direction="vertical" style={{ width: '100%' }} size={8}>
                <Input
                  placeholder="变量名称（如：不良贷款率）"
                  value={variable.name}
                  onChange={(e) =>
                    handleChange(index, 'name', e.target.value)
                  }
                />
                <Space.Compact style={{ width: '100%' }}>
                  <InputNumber
                    placeholder="当前值"
                    value={variable.current_value}
                    onChange={(v) => handleChange(index, 'current_value', v)}
                    style={{ width: '50%' }}
                  />
                  <Input
                    placeholder="单位（如：% / 亿元）"
                    value={variable.unit || ''}
                    onChange={(e) =>
                      handleChange(index, 'unit', e.target.value)
                    }
                    style={{ width: '50%' }}
                  />
                </Space.Compact>
                <Input
                  placeholder="目标条件（如：< 3% / 稳定）"
                  value={variable.target_condition || ''}
                  onChange={(e) =>
                    handleChange(index, 'target_condition', e.target.value)
                  }
                />
                <Input
                  placeholder="数据来源（如：年报 / 理杏仁 / 同花顺）"
                  value={variable.source ?? ''}
                  onChange={(e) =>
                    handleChange(index, 'source', e.target.value)
                  }
                />
              </Space>
            </Card>
          ))}
        </Space>
      )}
    </Modal>
  );
}
