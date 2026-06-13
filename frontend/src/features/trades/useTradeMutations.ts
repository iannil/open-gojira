import { reverseTrade } from '../../api/client';
import { useToastMutation } from '../../lib/useToastMutation';
import { cashKeys, tradeKeys } from './queries';

export function useReverseTradeMutation() {
  return useToastMutation((id: number) => reverseTrade(id), {
    successMsg: '已红冲',
    invalidate: () => [tradeKeys.all(), cashKeys.all(), ['cockpit'], ['holdings']],
  });
}
