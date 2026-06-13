import { useQuery } from '@tanstack/react-query';
import { listStrategies } from '../../api/client';
import { strategyKeys } from './queries';

/** Dictionary of all strategies (builtin + custom). Long stale window. */
export function useStrategiesQuery() {
  return useQuery({
    queryKey: strategyKeys.all(),
    queryFn: listStrategies,
    staleTime: 5 * 60_000,
  });
}
