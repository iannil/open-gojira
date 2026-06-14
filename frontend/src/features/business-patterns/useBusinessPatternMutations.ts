import {
  createBusinessPattern,
  deleteBusinessPattern,
  inferAllBusinessPatterns,
  updateBusinessPattern,
} from '../../api/client';
import type {
  BusinessPatternCreate,
  BusinessPatternUpdate,
  InferAllSummary,
} from '../../api/types';
import { useToastMutation } from '../../lib/useToastMutation';
import { businessPatternKeys } from './queries';

export function useCreateBusinessPatternMutation() {
  return useToastMutation(
    (payload: BusinessPatternCreate) => createBusinessPattern(payload),
    {
      successMsg: '商业模式已创建',
      invalidate: () => [businessPatternKeys.all()],
    },
  );
}

export function useUpdateBusinessPatternMutation() {
  return useToastMutation(
    (args: { id: number; payload: BusinessPatternUpdate }) =>
      updateBusinessPattern(args.id, args.payload),
    {
      successMsg: '商业模式已更新',
      invalidate: () => [businessPatternKeys.all()],
    },
  );
}

export function useDeleteBusinessPatternMutation() {
  return useToastMutation((id: number) => deleteBusinessPattern(id), {
    successMsg: '已删除',
    invalidate: () => [businessPatternKeys.all()],
  });
}

export function useInferAllBusinessPatternsMutation() {
  return useToastMutation<InferAllSummary, boolean>(
    (force: boolean) => inferAllBusinessPatterns(force),
    {
      successMsg: (r: InferAllSummary) =>
        `推断完成:共 ${r.total} 只,更新 ${r.updated},保护 ${r.protected},清空 ${r.cleared}`,
      errorMsg: '推断失败',
      invalidate: () => [businessPatternKeys.all()],
    },
  );
}
