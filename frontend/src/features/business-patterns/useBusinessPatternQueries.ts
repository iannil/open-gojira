import { useQuery } from '@tanstack/react-query';
import { listBusinessPatterns } from '../../api/client';
import { businessPatternKeys } from './queries';

export function useBusinessPatternsQuery() {
  return useQuery({
    queryKey: businessPatternKeys.all(),
    queryFn: () => listBusinessPatterns(),
    staleTime: 60_000,
  });
}
