import { useQuery } from '@tanstack/react-query';
import { listDrafts } from '../../api/client';
import { draftKeys, type DraftListFilter } from './queries';

/** Drafts list. Default filter is pending-only (today's actionable queue). */
export function useDraftsQuery(filter: DraftListFilter) {
  return useQuery({
    queryKey: draftKeys.list(filter),
    queryFn: () => listDrafts(filter),
    staleTime: 10_000,
  });
}
