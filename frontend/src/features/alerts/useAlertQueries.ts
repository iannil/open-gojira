import { useQuery } from '@tanstack/react-query';
import { listSystemAlerts } from '../../api/client';
import { alertKeys, type AlertListFilter } from './queries';

/**
 * Banner summary: all unresolved alerts (limit 500). Polled every 60s.
 * Mounted in Layout so every page sees fresh counts.
 */
export function useUnresolvedAlertsSummaryQuery() {
  return useQuery({
    queryKey: alertKeys.list({ unresolved_only: true, limit: 500 }),
    queryFn: () =>
      listSystemAlerts({ unresolved_only: true, limit: 500 }),
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
    staleTime: 10_000,
  });
}

/**
 * Detail tab: full list with user-applied filter. 10s stale window.
 */
export function useAlertsQuery(filter: AlertListFilter) {
  return useQuery({
    queryKey: alertKeys.list(filter),
    queryFn: () => listSystemAlerts(filter),
    staleTime: 10_000,
  });
}
