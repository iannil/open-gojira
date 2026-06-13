import {
  addToStockPool,
  cancelPipelineRun,
  executeCleanup,
  removeFromStockPool,
  retryPipelineRun,
  startPipelineRun,
} from '../../api/client';
import { useToastMutation } from '../../lib/useToastMutation';
import { dataMgmtKeys } from './queries';

/** Invalidate everything in the data-management subtree. */
const INVALIDATE_ALL = () => [dataMgmtKeys.all()];

export function useStartPipelineRunMutation() {
  return useToastMutation(
    (args: { pipelineType: string; config: Record<string, unknown> }) =>
      startPipelineRun(args.pipelineType, args.config),
    {
      successMsg: (res) => `已启动 Pipeline (Run: ${res.run_id})`,
      invalidate: INVALIDATE_ALL,
    },
  );
}

export function useRetryPipelineRunMutation() {
  return useToastMutation(
    (runId: string) => retryPipelineRun(runId),
    {
      successMsg: (res) => `已重试 (New Run: ${res.run_id})`,
      invalidate: INVALIDATE_ALL,
    },
  );
}

export function useCancelPipelineRunMutation() {
  return useToastMutation((runId: string) => cancelPipelineRun(runId), {
    successMsg: '已请求取消',
    invalidate: INVALIDATE_ALL,
  });
}

export function useAddToStockPoolMutation() {
  return useToastMutation((codes: string[]) => addToStockPool(codes), {
    successMsg: (res) => `已添加 ${res.added} 只股票`,
    invalidate: INVALIDATE_ALL,
  });
}

export function useRemoveFromStockPoolMutation() {
  return useToastMutation((codes: string[]) => removeFromStockPool(codes), {
    successMsg: (res) => `已移除 ${res.removed} 只股票`,
    invalidate: INVALIDATE_ALL,
  });
}

export function useExecuteCleanupMutation() {
  return useToastMutation(
    (args: { dataType: string; params: { after_date: string; before_date: string } }) =>
      executeCleanup(args.dataType, args.params),
    {
      successMsg: (res) => `已清理 ${res.deleted_count} 条记录`,
      invalidate: INVALIDATE_ALL,
    },
  );
}
