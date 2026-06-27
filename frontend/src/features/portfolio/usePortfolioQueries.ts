import { useQuery } from '@tanstack/react-query';

import { fetchEvaluation, fetchPortfolioSummary } from '../../api/client';
import { portfolioKeys } from './queries';

export function usePortfolioSummaryQuery() {
  return useQuery({
    queryKey: portfolioKeys.summary(),
    queryFn: fetchPortfolioSummary,
    refetchInterval: 60_000,
  });
}

export function usePortfolioEvaluationQuery() {
  return useQuery({
    queryKey: portfolioKeys.evaluation(),
    queryFn: fetchEvaluation,
    refetchInterval: 120_000,
  });
}
