import {
  createStrategy,
  deleteStrategy,
  testStrategy,
  updateStrategy,
} from '../../api/client';
import type { StrategyCreate, StrategyUpdate, StrategyTestResponse } from '../../api/types';
import { useToastMutation } from '../../lib/useToastMutation';
import { strategyKeys } from './queries';

export function useCreateStrategyMutation() {
  return useToastMutation((payload: StrategyCreate) => createStrategy(payload), {
    successMsg: '策略已创建',
    invalidate: () => [strategyKeys.all()],
  });
}

export function useUpdateStrategyMutation() {
  return useToastMutation(
    (args: { id: number; payload: StrategyUpdate }) =>
      updateStrategy(args.id, args.payload),
    {
      successMsg: '策略已更新',
      invalidate: () => [strategyKeys.all()],
    },
  );
}

export function useDeleteStrategyMutation() {
  return useToastMutation((id: number) => deleteStrategy(id), {
    successMsg: '已删除',
    invalidate: () => [strategyKeys.all()],
  });
}

/** Test strategy against a stock. Success toast reports pass/fail so the
 * user gets feedback even if they navigated away from the modal. */
export function useTestStrategyMutation() {
  return useToastMutation(
    (args: { id: number; code: string }) => testStrategy(args.id, args.code),
    {
      successMsg: (r: StrategyTestResponse) => (r.passed ? '✓ 通过' : '✗ 未通过'),
      errorMsg: '测试失败',
    },
  );
}
