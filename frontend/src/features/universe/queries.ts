export type FullUniverseFilter = {
  page?: number;
  page_size?: number;
  pe_pct_max?: number;
  pb_pct_max?: number;
  dyr_min?: number;
  pe_ttm_min?: number;
  pe_ttm_max?: number;
  pb_min?: number;
  pb_max?: number;
  industry?: string;
  keyword?: string;
};

export const universeKeys = {
  all: () => ['universe'] as const,
  my: () => [...universeKeys.all(), 'my'] as const,
  stats: () => [...universeKeys.all(), 'stats'] as const,
  full: (filter: FullUniverseFilter) =>
    [...universeKeys.all(), 'full', filter] as const,
} as const;
