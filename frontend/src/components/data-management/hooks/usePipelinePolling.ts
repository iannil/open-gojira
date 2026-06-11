import { useCallback, useEffect, useRef, useState } from 'react';

import { getPipelineRun } from '../../../api/client';
import type { PipelineRunDetail } from '../../../api/types';
import { POLL_INTERVAL_MS } from '../constants';

export interface PipelinePollingState {
  activeRun: PipelineRunDetail | null;
  isPolling: boolean;
  startPolling: (runId: string) => void;
  stopPolling: () => void;
}

export function usePipelinePolling(): PipelinePollingState {
  const [activeRun, setActiveRun] = useState<PipelineRunDetail | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const runIdRef = useRef<string | null>(null);

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    runIdRef.current = null;
    setIsPolling(false);
  }, []);

  const poll = useCallback(async () => {
    const rid = runIdRef.current;
    if (!rid) return;
    try {
      const run = await getPipelineRun(rid);
      setActiveRun(run);
      if (run.status !== 'pending' && run.status !== 'running') {
        stopPolling();
      }
    } catch {
      stopPolling();
    }
  }, [stopPolling]);

  const startPolling = useCallback((runId: string) => {
    stopPolling();
    runIdRef.current = runId;
    setIsPolling(true);
    // initial fetch
    poll();
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS);
  }, [stopPolling, poll]);

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  return { activeRun, isPolling, startPolling, stopPolling };
}
