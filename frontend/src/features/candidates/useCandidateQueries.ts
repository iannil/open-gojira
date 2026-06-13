import { useQuery } from '@tanstack/react-query';
import { listCandidates } from '../../api/client';
import { candidateKeys } from './queries';

/**
 * Server query is intentionally filter-free; all multi-field filtering is
 * done client-side on the cached list (per design: client-side filtering
 * for candidates keeps cache reuse high and avoids re-fetching on every
 * keystroke).
 */
export function useCandidatesQuery() {
  return useQuery({
    queryKey: candidateKeys.list({}),
    queryFn: () => listCandidates({}),
    staleTime: 30_000,
  });
}
