import { useState } from 'react';
import { Button, Card, DatePicker, Radio, Space, Statistic, Typography } from 'antd';
import { DeleteOutlined, EyeOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';

import { previewCleanup } from '../../../api/client';
import { useAntdStatic } from '../../../hooks/useAntdStatic';
import { useDataStatusQuery } from '../useDataQueries';
import { useExecuteCleanupMutation } from '../useDataMutations';
import { DATA_TYPE_LABELS, type DataTypeKey } from '../constants';

const { Text } = Typography;

export default function DataCleanupPanel() {
  const { message } = useAntdStatic();
  const statusQ = useDataStatusQuery();
  const cleanupM = useExecuteCleanupMutation();

  const [dataType, setDataType] = useState<DataTypeKey>('valuations');
  const [dateRange, setDateRange] = useState<
    [dayjs.Dayjs | null, dayjs.Dayjs | null] | null
  >(null);
  const [previewCount, setPreviewCount] = useState<number | null>(null);
  const [previewing, setPreviewing] = useState(false);

  const storageData = statusQ.data;

  const handlePreview = async () => {
    if (!dateRange?.[0] || !dateRange?.[1]) {
      message.warning('请选择日期范围');
      return;
    }
    setPreviewing(true);
    try {
      const res = await previewCleanup(dataType, {
        after_date: dateRange[0].format('YYYY-MM-DD'),
        before_date: dateRange[1].format('YYYY-MM-DD'),
      });
      setPreviewCount(res.record_count);
    } catch {
      message.error('预览失败');
    } finally {
      setPreviewing(false);
    }
  };

  const handleCleanup = async () => {
    if (!dateRange?.[0] || !dateRange?.[1]) {
      message.warning('请选择日期范围');
      return;
    }
    await cleanupM.mutateAsync({
      dataType,
      params: {
        after_date: dateRange[0].format('YYYY-MM-DD'),
        before_date: dateRange[1].format('YYYY-MM-DD'),
      },
    });
    setPreviewCount(null);
    setDateRange(null);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
      <Card className="gojira-card" bordered={false} title="存储用量概览" size="small">
        <Space size="large">
          {storageData &&
            (Object.keys(DATA_TYPE_LABELS) as DataTypeKey[]).map((key) => (
              <Statistic
                key={key}
                title={DATA_TYPE_LABELS[key]}
                value={storageData[key]?.total_records ?? 0}
                suffix="条"
              />
            ))}
        </Space>
      </Card>

      <Card className="gojira-card" bordered={false} title="数据清理" size="small">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
          <div>
            <Text type="secondary" style={{ display: 'block', marginBottom: 'var(--sp-2)' }}>
              选择数据类型
            </Text>
            <Radio.Group
              value={dataType}
              onChange={(e) => {
                setDataType(e.target.value);
                setPreviewCount(null);
              }}
              optionType="button"
              buttonStyle="solid"
            >
              {Object.entries(DATA_TYPE_LABELS).map(([k, v]) => (
                <Radio.Button key={k} value={k}>
                  {v}
                </Radio.Button>
              ))}
            </Radio.Group>
          </div>

          <div>
            <Text type="secondary" style={{ display: 'block', marginBottom: 'var(--sp-2)' }}>
              选择时间范围
            </Text>
            <DatePicker.RangePicker
              style={{ width: 400 }}
              value={dateRange}
              onChange={(dates) => {
                setDateRange(
                  dates as [dayjs.Dayjs | null, dayjs.Dayjs | null] | null,
                );
                setPreviewCount(null);
              }}
            />
          </div>

          <Space>
            <Button
              icon={<EyeOutlined />}
              onClick={handlePreview}
              loading={previewing}
              disabled={!dateRange?.[0] || !dateRange?.[1]}
            >
              预览清理数量
            </Button>
            {previewCount !== null && (
              <Button
                type="primary"
                danger
                icon={<DeleteOutlined />}
                onClick={handleCleanup}
                loading={cleanupM.isPending}
              >
                确认清理 (<span className="num">{previewCount}</span> 条)
              </Button>
            )}
          </Space>

          {previewCount !== null && (
            <Text>
              将清理 <Text strong><span className="num">{previewCount}</span></Text> 条{' '}
              {DATA_TYPE_LABELS[dataType]} 记录
            </Text>
          )}
        </div>
      </Card>
    </div>
  );
}
