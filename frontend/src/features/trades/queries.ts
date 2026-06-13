export type TradeListFilter = {
  code?: string;
  side?: string;
  source?: string;
  limit?: number;
};

export const tradeKeys = {
  all: () => ['trades'] as const,
  list: (filter: TradeListFilter) => [...tradeKeys.all(), 'list', filter] as const,
} as const;

export const cashKeys = {
  all: () => ['cash'] as const,
  balance: () => [...cashKeys.all(), 'balance'] as const,
} as const;
