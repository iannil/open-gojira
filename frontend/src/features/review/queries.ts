export const reviewKeys = {
  all: () => ['review'] as const,
  monthly: (month: string) => [...reviewKeys.all(), 'monthly', month] as const,
  quarterly: (year: number, q: number) =>
    [...reviewKeys.all(), 'quarterly', year, q] as const,
  annual: (year: number) => [...reviewKeys.all(), 'annual', year] as const,
} as const;
