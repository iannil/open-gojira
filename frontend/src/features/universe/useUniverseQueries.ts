import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { fetchFullUniverse, fetchUniverse, fetchUniverseStats } from '../../api/client';
import { universeKeys, type FullUniverseFilter } from './queries';

/** My Universe: client-side-filtered personal subscription list. */
export function useMyUniverseQuery() {
  return useQuery({
    queryKey: universeKeys.my(),
    queryFn: fetchUniverse,
    staleTime: 30_000,
  });
}

/** Full market: server-side paginated + filtered. keepPreviousData prevents
 * flicker when filter/page params change. */
export function useFullUniverseQuery(filter: FullUniverseFilter) {
  return useQuery({
    queryKey: universeKeys.full(filter),
    queryFn: () =>
      fetchFullUniverse({
        page: filter.page ?? 1,
        page_size: filter.page_size ?? 50,
        pe_pct_max: filter.pe_pct_max,
        pb_pct_max: filter.pb_pct_max,
        dyr_min: filter.dyr_min,
        pe_ttm_min: filter.pe_ttm_min,
        pe_ttm_max: filter.pe_ttm_max,
        pb_min: filter.pb_min,
        pb_max: filter.pb_max,
        industry: filter.industry,
        keyword: filter.keyword,
      }),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}

/** Coverage stats — determines if full-market mode is available. */
export function useUniverseStatsQuery() {
  return useQuery({
    queryKey: universeKeys.stats(),
    queryFn: fetchUniverseStats,
    staleTime: 60_000,
  });
}
