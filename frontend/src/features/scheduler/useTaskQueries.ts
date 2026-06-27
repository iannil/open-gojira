import { useQuery } from '@tanstack/react-query';
import {
  listTasks,
  listTaskRuns,
  taskHealth,
} from '../../api/client';
import { taskKeys } from './taskQueries';

export function useTasksQuery() {
  return useQuery({
    queryKey: taskKeys.list(),
    queryFn: listTasks,
    staleTime: 30_000,
  });
}

export function useTaskRunsQuery(params?: {
  task_id?: string;
  status?: string;
  limit?: number;
}) {
  return useQuery({
    queryKey: taskKeys.runs(params),
    queryFn: () => listTaskRuns(params),
    staleTime: 10_000,
  });
}

export function useTaskHealthQuery() {
  return useQuery({
    queryKey: taskKeys.health(),
    queryFn: taskHealth,
    staleTime: 15_000,
  });
}
