import { useQuery } from '@tanstack/react-query';
import {
  fetchAnnualReview,
  fetchMonthlyReview,
  fetchQuarterlyReview,
} from '../../api/client';
import { reviewKeys } from './queries';

export function useMonthlyReviewQuery(month: string) {
  return useQuery({
    queryKey: reviewKeys.monthly(month),
    queryFn: () => fetchMonthlyReview({ month }),
    staleTime: 60_000,
  });
}

export function useQuarterlyReviewQuery(year: number, q: number) {
  return useQuery({
    queryKey: reviewKeys.quarterly(year, q),
    queryFn: () => fetchQuarterlyReview(year, q),
    staleTime: 60_000,
  });
}

export function useAnnualReviewQuery(year: number) {
  return useQuery({
    queryKey: reviewKeys.annual(year),
    queryFn: () => fetchAnnualReview(year),
    staleTime: 60_000,
  });
}
