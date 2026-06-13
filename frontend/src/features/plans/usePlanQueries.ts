import { useQuery } from '@tanstack/react-query';
import { listPlans, listStrategies } from '../../api/client';
import { planKeys, strategiesKey } from './queries';

export function usePlansQuery() {
  return useQuery({
    queryKey: planKeys.all(),
    queryFn: listPlans,
    staleTime: 30_000,
  });
}

export function useStrategiesQuery() {
  return useQuery({
    queryKey: strategiesKey(),
    queryFn: listStrategies,
    staleTime: 5 * 60_000,
  });
}
