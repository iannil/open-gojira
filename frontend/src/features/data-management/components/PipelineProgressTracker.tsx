import { Progress, Space, Typography } from 'antd';

import type { PipelineRunDetail } from '../../../api/types';

const { Text } = Typography;

interface Props {
  run: PipelineRunDetail;
}

export default function PipelineProgressTracker({ run }: Props) {
  const pct = Math.min(run.progress, 100);
  const status =
    run.status === 'failed'
      ? 'exception'
      : run.status === 'completed'
        ? 'success'
        : 'active';

  return (
    <div style={{ marginTop: 12 }}>
      <Progress percent={pct} status={status} />
      <Space>
        <Text type="secondary">
          已处理 <span className="num">{run.completed_items + run.failed_items}</span> /{' '}
          <span className="num">{run.total_items}</span> 只
        </Text>
        {run.failed_items > 0 && (
          <Text type="danger">
            (<span className="num">{run.failed_items}</span> 失败)
          </Text>
        )}
      </Space>
    </div>
  );
}
