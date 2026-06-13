export type DraftListFilter = {
  status?: 'pending' | 'executed' | 'cancelled';
  code?: string;
  limit?: number;
};

export const draftKeys = {
  all: () => ['drafts'] as const,
  list: (filter: DraftListFilter) => [...draftKeys.all(), 'list', filter] as const,
} as const;
