import { useQuery } from '@tanstack/react-query';
import { listNotificationChannels, listRiskRules } from '../../api/client';
import { monitoringKeys } from './queries';

export function useNotificationChannelsQuery() {
  return useQuery({
    queryKey: monitoringKeys.channels(),
    queryFn: () => listNotificationChannels(),
    staleTime: 30_000,
  });
}

export function useRiskRulesQuery() {
  return useQuery({
    queryKey: monitoringKeys.riskRules(),
    queryFn: () => listRiskRules(),
    staleTime: 30_000,
  });
}
