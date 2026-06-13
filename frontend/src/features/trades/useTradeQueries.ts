import { useQuery } from '@tanstack/react-query';
import { getCashBalance, listTrades } from '../../api/client';
import { cashKeys, tradeKeys, type TradeListFilter } from './queries';

export function useTradesQuery(filter: TradeListFilter) {
  return useQuery({
    queryKey: tradeKeys.list(filter),
    queryFn: () => listTrades(filter),
    staleTime: 10_000,
  });
}

export function useCashBalanceQuery() {
  return useQuery({
    queryKey: cashKeys.balance(),
    queryFn: getCashBalance,
    staleTime: 10_000,
  });
}
