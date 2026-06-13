import { useQuery } from '@tanstack/react-query';
import { fetchCashflowGoal, fetchCockpit, getThemeExposure } from '../../api/client';
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
