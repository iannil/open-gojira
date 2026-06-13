import { useQuery } from '@tanstack/react-query';
import { listJobExecutions, listSchedulerJobs } from '../../api/client';
import { schedulerKeys } from './queries';

export function useSchedulerJobsQuery() {
  return useQuery({
    queryKey: schedulerKeys.jobs(),
    queryFn: listSchedulerJobs,
    staleTime: 30_000,
  });
}

export function useJobExecutionsQuery(limit = 100) {
  return useQuery({
    queryKey: schedulerKeys.executions(limit),
    queryFn: () => listJobExecutions(undefined, limit),
    staleTime: 10_000,
  });
}
