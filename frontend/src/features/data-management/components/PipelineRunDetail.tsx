import { Descriptions, Drawer, Table, Tag, Typography } from 'antd';

import { defaultPagination } from '../../../lib/pagination';
import type { PipelineRunDetail as RunDetail } from '../../../api/types';
import { DATA_TYPE_LABELS, PIPELINE_STATUS_COLORS, PIPELINE_STATUS_LABELS } from '../constants';

const { Text } = Typography;

interface Props {
  run: RunDetail | null;
  open: boolean;
  onClose: () => void;
}

export default function PipelineRunDetailDrawer({ run, open, onClose }: Props) {
  if (!run) return null;

  const failedEntries =
    run.summary?.failed_codes?.map((code: string, i: number) => ({
      code,
      error: run.summary?.failed_errors?.[code] ?? 'Unknown error',
      key: i,
    })) ?? [];

  return (
    <Drawer title="Pipeline 运行详情" open={open} onClose={onClose} width={600}>
      <Descriptions column={2} bordered size="small">
        <Descriptions.Item label="Run ID">
          <Text code>{run.run_id}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="类型">
          {DATA_TYPE_LABELS[run.pipeline_type as keyof typeof DATA_TYPE_LABELS] ?? run.pipeline_type}
        </Descriptions.Item>
        <Descriptions.Item label="状态">
          <Tag color={PIPELINE_STATUS_COLORS[run.status]}>
            {PIPELINE_STATUS_LABELS[run.status] ?? run.status}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="进度">
          <span className="num">{run.completed_items}</span>/
          <span className="num">{run.total_items}</span> (
          <span className="num">{run.failed_items}</span> 失败)
        </Descriptions.Item>
        <Descriptions.Item label="开始时间">{run.started_at ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="结束时间">{run.finished_at ?? '-'}</Descriptions.Item>
        {run.config && (
          <>
            <Descriptions.Item label="股票范围">
              {run.config.stock_codes ? (
                <>
                  <span className="num">{run.config.stock_codes.length}</span> 只
                </>
              ) : (
                '全部'
              )}
            </Descriptions.Item>
            <Descriptions.Item label="年数">
              <span className="num">{run.config.years ?? '-'}</span>
            </Descriptions.Item>
          </>
        )}
        {run.summary?.duration_seconds != null && (
          <Descriptions.Item label="耗时" span={2}>
            <span className="num">{run.summary.duration_seconds.toFixed(1)}</span> 秒
          </Descriptions.Item>
        )}
      </Descriptions>

      {failedEntries.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <Text strong>失败股票列表</Text>
          <Table
            dataSource={failedEntries}
            size="small"
            pagination={{ ...defaultPagination, defaultPageSize: 20 }}
            columns={[
              {
                title: '股票代码',
                dataIndex: 'code',
                key: 'code',
                render: (v: string) => <Text code>{v}</Text>,
              },
              { title: '错误信息', dataIndex: 'error', key: 'error', ellipsis: true },
            ]}
          />
        </div>
      )}
    </Drawer>
  );
}
