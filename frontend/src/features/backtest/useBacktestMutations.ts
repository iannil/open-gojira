import { submitBacktest } from '../../api/client';
import type { BacktestConfig, BacktestRun } from '../../api/types';
import { useToastMutation } from '../../lib/useToastMutation';
import { backtestKeys } from './queries';

export function useSubmitBacktestMutation() {
  return useToastMutation((config: BacktestConfig) => submitBacktest(config), {
    successMsg: (r: BacktestRun) =>
      r.status === 'completed'
        ? `回测完成 #${r.id}`
        : r.status === 'failed'
          ? `回测失败 #${r.id} — 请查看错误信息`
          : `已提交 #${r.id}`,
    invalidate: () => [backtestKeys.all()],
  });
}
