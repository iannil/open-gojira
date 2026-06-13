import { useQuery } from '@tanstack/react-query';
import {
  fetchMarginTrading,
  fetchNorthFlow,
  fetchRevenueComposition,
  fetchShareholders,
  getStock,
  listCandidates,
  listHoldings,
} from '../../api/client';
import { stockKeys } from './queries';

/** All queries gated by `enabled: !!code` so they suspend until the route
 * param resolves. Each tab/consumer picks its own query; they all run in
 * parallel automatically and cache independently. */

export function useStockQuery(code: string | undefined) {
  return useQuery({
    queryKey: stockKeys.detail(code ?? ''),
    queryFn: () => getStock(code!),
    enabled: !!code,
    staleTime: 60_000,
  });
}

export function useStockCandidatesQuery(code: string | undefined) {
  return useQuery({
    queryKey: stockKeys.candidates(code ?? ''),
    queryFn: async () => {
      const all = await listCandidates({ status: 'active' });
      return all.filter((c) => c.stock_code === code);
    },
    enabled: !!code,
    staleTime: 30_000,
  });
}

export function useStockHoldingsQuery(code: string | undefined) {
  return useQuery({
    queryKey: stockKeys.holdings(code ?? ''),
    queryFn: async () => {
      const all = await listHoldings();
      return all.filter((h) => h.stock_code === code && !h.sell_date);
    },
    enabled: !!code,
    staleTime: 30_000,
  });
}

export function useShareholdersQuery(code: string | undefined) {
  return useQuery({
    queryKey: stockKeys.shareholders(code ?? ''),
    queryFn: () => fetchShareholders(code!),
    enabled: !!code,
    staleTime: 5 * 60_000,
    retry: 0,
  });
}

export function useNorthFlowQuery(code: string | undefined) {
  return useQuery({
    queryKey: stockKeys.northFlow(code ?? ''),
    queryFn: () => fetchNorthFlow(code!),
    enabled: !!code,
    staleTime: 5 * 60_000,
    retry: 0,
  });
}

export function useMarginTradingQuery(code: string | undefined) {
  return useQuery({
    queryKey: stockKeys.margin(code ?? ''),
    queryFn: () => fetchMarginTrading(code!),
    enabled: !!code,
    staleTime: 5 * 60_000,
    retry: 0,
  });
}

export function useRevenueCompositionQuery(code: string | undefined) {
  return useQuery({
    queryKey: stockKeys.revenue(code ?? ''),
    queryFn: () => fetchRevenueComposition(code!),
    enabled: !!code,
    staleTime: 5 * 60_000,
    retry: 0,
  });
}
