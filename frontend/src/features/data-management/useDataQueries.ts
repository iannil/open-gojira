import { useQuery } from '@tanstack/react-query';
import {
  fetchApiUsage,
  fetchDataQuality,
  fetchDataStatus,
  fetchDeadLetterStats,
  fetchPipelineHealth,
  fetchStockPool,
  fetchUniverseStats,
  getPipelineRun,
  listPipelineRuns,
} from '../../api/client';
import { dataMgmtKeys } from './queries';

/** Top-of-page banner: full_coverage mode + total / coverage counts. */
export function useUniverseStatsQuery() {
  return useQuery({
    queryKey: dataMgmtKeys.stats(),
    queryFn: fetchUniverseStats,
    staleTime: 30_000,
  });
}

/** Per-data-type record counts. */
export function useDataStatusQuery() {
  return useQuery({
    queryKey: dataMgmtKeys.status(),
    queryFn: fetchDataStatus,
    staleTime: 30_000,
  });
}

/** Pipeline freshness flags per data type. */
export function usePipelineHealthQuery() {
  return useQuery({
    queryKey: dataMgmtKeys.health(),
    queryFn: fetchPipelineHealth,
    staleTime: 30_000,
  });
}

/** Today's API call volume + cache hit + monthly budget. */
export function useApiUsageQuery() {
  return useQuery({
    queryKey: dataMgmtKeys.apiUsage(),
    queryFn: fetchApiUsage,
    staleTime: 30_000,
  });
}

/** Dead letter queue aggregate counts. */
export function useDeadLetterStatsQuery() {
  return useQuery({
    queryKey: dataMgmtKeys.deadLetter(),
    queryFn: () => fetchDeadLetterStats(),
    staleTime: 30_000,
  });
}

/** Quality score + per-data-type quality + recommendations. */
export function useDataQualityQuery() {
  return useQuery({
    queryKey: dataMgmtKeys.quality(),
    queryFn: fetchDataQuality,
    staleTime: 30_000,
  });
}

/** Pipeline run history (paginated by limit). */
export function usePipelineRunsQuery(limit = 30) {
  return useQuery({
    queryKey: dataMgmtKeys.pipelineRuns(limit),
    queryFn: () => listPipelineRuns({ limit }),
    staleTime: 10_000,
  });
}

/**
 * Single pipeline run with polling. Polls every 2s while the run is pending
 * or running; stops when terminal. Replaces the old usePipelinePolling hook.
 */
export function useActivePipelineRunQuery(runId: string | null) {
  return useQuery({
    queryKey: runId
      ? dataMgmtKeys.pipelineRun(runId)
      : ['data-management', 'pipeline-run', null],
    queryFn: () => getPipelineRun(runId!),
    enabled: !!runId,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 2000;
      return data.status === 'pending' || data.status === 'running' ? 2000 : false;
    },
  });
}

/** Stock pool list (manual mode). */
export function useStockPoolQuery() {
  return useQuery({
    queryKey: dataMgmtKeys.stockPool(),
    queryFn: fetchStockPool,
    staleTime: 30_000,
  });
}
