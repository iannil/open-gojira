import { useStrategiesQuery } from '../strategies/useStrategyQueries';
import { useQuery } from '@tanstack/react-query';
import { listPlans } from '../../api/client';
import { planKeys } from './queries';

export function usePlansQuery() {
  return useQuery({
    queryKey: planKeys.all(),
    queryFn: listPlans,
    staleTime: 30_000,
  });
}

/** Strategies query is owned by the strategies feature. Re-exported here
 * for plans callers (PlanForm needs strategy list for the dropdown). */
export { useStrategiesQuery };
