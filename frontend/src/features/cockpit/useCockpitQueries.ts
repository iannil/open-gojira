import { useQuery } from '@tanstack/react-query';
import { fetchCashflowGoal, fetchCockpit, getThemeExposure, listSystemAlerts } from '../../api/client';
import { cockpitKeys } from './queries';

/** Main aggregator: cashflow goal / drafts / holdings / quadrant / alerts /
 * plans / dividend projection / cycle / thesis alerts. Short stale window
 * (financial data). */
export function useCockpitQuery() {
  return useQuery({
    queryKey: cockpitKeys.summary(),
    queryFn: fetchCockpit,
    staleTime: 10_000,
  });
}

/** Theme exposure breakdown (separate slow endpoint). */
export function useThemeExposureQuery() {
  return useQuery({
    queryKey: cockpitKeys.themeExposure(),
    queryFn: getThemeExposure,
    staleTime: 60_000,
    retry: 0,
  });
}

/** Cashflow goal (used by GoalEditor modal). */
export function useCashflowGoalQuery() {
  return useQuery({
    queryKey: cockpitKeys.cashflowGoal(),
    queryFn: fetchCashflowGoal,
    staleTime: 60_000,
  });
}

/** Critical unresolved system alerts — for top-of-page banner (Q15 B-min).
 * Long stale time since alerts are emitted server-side and resolving them
 * requires user action; no need to refetch frequently. */
export function useCriticalAlertsQuery() {
  return useQuery({
    queryKey: cockpitKeys.criticalAlerts(),
    queryFn: () => listSystemAlerts({ severity: 'critical', unresolved_only: true }),
    staleTime: 60_000,
    retry: 0,
  });
}
