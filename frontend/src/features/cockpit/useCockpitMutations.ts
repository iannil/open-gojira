import { updateCashflowGoal } from '../../api/client';
import type { CashflowGoalUpdate } from '../../api/types';
import { useToastMutation } from '../../lib/useToastMutation';
import { cockpitKeys } from './queries';

/** Update cashflow goal. Invalidates cockpit summary + cashflow goal. */
export function useUpdateCashflowGoalMutation() {
  return useToastMutation((payload: CashflowGoalUpdate) => updateCashflowGoal(payload), {
    successMsg: '目标已更新',
    invalidate: () => [cockpitKeys.all()],
  });
}
