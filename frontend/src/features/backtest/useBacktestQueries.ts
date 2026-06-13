import { useQuery } from '@tanstack/react-query';
import { listBacktests } from '../../api/client';
import { backtestKeys } from './queries';

export function useBacktestHistoryQuery(limit = 20) {
  return useQuery({
    queryKey: backtestKeys.history(limit),
    queryFn: () => listBacktests(limit),
    staleTime: 30_000,
  });
}
