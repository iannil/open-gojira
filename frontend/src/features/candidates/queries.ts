export type CandidateListFilter = {
  plan_id?: number;
  status?: string;
};

export const candidateKeys = {
  all: () => ['candidates'] as const,
  list: (filter: CandidateListFilter) =>
    [...candidateKeys.all(), 'list', filter] as const,
} as const;
