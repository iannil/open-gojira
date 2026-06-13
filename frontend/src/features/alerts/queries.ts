export type AlertListFilter = {
  severity?: 'critical' | 'warning' | 'info';
  category?: 'data' | 'scheduler' | 'api' | 'db' | 'token';
  unresolved_only?: boolean;
  limit?: number;
};

export const alertKeys = {
  all: () => ['system-alerts'] as const,
  list: (filter: AlertListFilter) =>
    [...alertKeys.all(), 'list', filter] as const,
} as const;
