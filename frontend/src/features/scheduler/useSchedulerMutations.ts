import { triggerSchedulerJob, updateSchedulerJob } from '../../api/client';
import type { SchedulerJobUpdate } from '../../api/types';
import { useToastMutation } from '../../lib/useToastMutation';
import { schedulerKeys } from './queries';

export function useUpdateSchedulerJobMutation() {
  return useToastMutation(
    (args: { jobId: string; payload: SchedulerJobUpdate }) =>
      updateSchedulerJob(args.jobId, args.payload),
    {
      successMsg: (data) => (data.enabled === false ? '已停用' : '已更新'),
      invalidate: () => [schedulerKeys.all()],
    },
  );
}

export function useTriggerSchedulerJobMutation() {
  return useToastMutation((jobId: string) => triggerSchedulerJob(jobId), {
    successMsg: '执行完成',
    invalidate: () => [schedulerKeys.all()],
  });
}
