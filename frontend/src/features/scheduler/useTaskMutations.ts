import {
  triggerTask,
  pauseTask,
  resumeTask,
  cancelTaskRun,
  retryTaskRun,
  updateTask,
} from '../../api/client';
import type { TaskUpdate } from '../../api/types';
import { useToastMutation } from '../../lib/useToastMutation';
import { taskKeys } from './taskQueries';

export function useTriggerTaskMutation() {
  return useToastMutation((taskId: string) => triggerTask(taskId), {
    successMsg: '任务已触发',
    invalidate: () => [taskKeys.all()],
  });
}

export function usePauseTaskMutation() {
  return useToastMutation((taskId: string) => pauseTask(taskId), {
    successMsg: '任务已暂停',
    invalidate: () => [taskKeys.all()],
  });
}

export function useResumeTaskMutation() {
  return useToastMutation((taskId: string) => resumeTask(taskId), {
    successMsg: '任务已恢复',
    invalidate: () => [taskKeys.all()],
  });
}

export function useCancelTaskRunMutation() {
  return useToastMutation((runId: number) => cancelTaskRun(runId), {
    successMsg: '运行已取消',
    invalidate: () => [taskKeys.all()],
  });
}

export function useRetryTaskRunMutation() {
  return useToastMutation((runId: number) => retryTaskRun(runId), {
    successMsg: '重试已触发',
    invalidate: () => [taskKeys.all()],
  });
}

export function useUpdateTaskMutation() {
  return useToastMutation(
    (args: { taskId: string; payload: TaskUpdate }) =>
      updateTask(args.taskId, args.payload),
    {
      successMsg: '任务配置已更新',
      invalidate: () => [taskKeys.all()],
    },
  );
}
