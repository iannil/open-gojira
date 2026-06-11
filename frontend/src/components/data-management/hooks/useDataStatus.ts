import { useCallback, useEffect, useState } from 'react';

import {
  fetchApiUsage,
  fetchDataStatus,
  fetchDeadLetterStats,
  fetchPipelineHealth,
} from '../../../api/client';
import type {
  ApiUsageResponse,
  DataStatusOverview,
  DeadLetterStatsResponse,
  PipelineHealthResponse,
} from '../../../api/types';

export interface DataStatusBundle {
  status: DataStatusOverview | null;
  health: PipelineHealthResponse | null;
  apiUsage: ApiUsageResponse | null;
  deadLetterStats: DeadLetterStatsResponse | null;
  loading: boolean;
  refresh: () => void;
}

export function useDataStatus(refreshKey: number): DataStatusBundle {
  const [status, setStatus] = useState<DataStatusOverview | null>(null);
  const [health, setHealth] = useState<PipelineHealthResponse | null>(null);
  const [apiUsage, setApiUsage] = useState<ApiUsageResponse | null>(null);
  const [deadLetterStats, setDeadLetterStats] = useState<DeadLetterStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, h, u, d] = await Promise.all([
        fetchDataStatus(),
        fetchPipelineHealth(),
        fetchApiUsage(),
        fetchDeadLetterStats(),
      ]);
      setStatus(s);
      setHealth(h);
      setApiUsage(u);
      setDeadLetterStats(d);
    } catch {
      // individual errors handled silently, data stays null
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  return { status, health, apiUsage, deadLetterStats, loading, refresh: load };
}
