export const dataMgmtKeys = {
  all: () => ['data-management'] as const,
  stats: () => [...dataMgmtKeys.all(), 'universe-stats'] as const,
  status: () => [...dataMgmtKeys.all(), 'status'] as const,
  health: () => [...dataMgmtKeys.all(), 'health'] as const,
  apiUsage: () => [...dataMgmtKeys.all(), 'api-usage'] as const,
  deadLetter: () => [...dataMgmtKeys.all(), 'dead-letter'] as const,
  quality: () => [...dataMgmtKeys.all(), 'quality'] as const,
  pipelineRuns: (limit: number) =>
    [...dataMgmtKeys.all(), 'pipeline-runs', limit] as const,
  pipelineRun: (runId: string) =>
    [...dataMgmtKeys.all(), 'pipeline-run', runId] as const,
  stockPool: () => [...dataMgmtKeys.all(), 'stock-pool'] as const,
} as const;
