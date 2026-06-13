import { createPlan, deletePlan, runPlan, updatePlan } from '../../api/client';
import type { PlanCreate, PlanResponse } from '../../api/types';
import { useToastMutation } from '../../lib/useToastMutation';
import { planKeys } from './queries';

type PlanRunResult = { passed?: number; drafts_emitted?: number };

export const useCreatePlanMutation = () =>
  useToastMutation(
    (payload: PlanCreate) => createPlan(payload),
    { successMsg: '预案已创建', invalidate: () => [planKeys.all()] },
  );

export const useRunPlanMutation = () =>
  useToastMutation(
    async (id: number) => (await runPlan(id)) as PlanRunResult,
    {
      successMsg: (r) =>
        `扫描完成: ${r.passed ?? 0} 只通过, ${r.drafts_emitted ?? 0} 条草稿`,
      invalidate: () => [planKeys.all(), ['candidates'], ['cockpit']],
    },
  );

export const useTogglePlanMutation = () =>
  useToastMutation(
    (vars: { id: number; status: 'active' | 'paused' }) =>
      updatePlan(vars.id, { status: vars.status }),
    {
      successMsg: (r: PlanResponse) => (r.status === 'active' ? '已启用' : '已暂停'),
      invalidate: () => [planKeys.all()],
    },
  );

export const useDeletePlanMutation = () =>
  useToastMutation(
    (id: number) => deletePlan(id),
    { successMsg: '已删除', invalidate: () => [planKeys.all()] },
  );
