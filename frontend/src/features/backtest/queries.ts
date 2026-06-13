export const backtestKeys = {
  all: () => ['backtests'] as const,
  history: (limit: number) => [...backtestKeys.all(), 'history', limit] as const,
} as const;
