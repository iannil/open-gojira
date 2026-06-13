export const stockKeys = {
  all: () => ['stock'] as const,
  detail: (code: string) => [...stockKeys.all(), 'detail', code] as const,
  candidates: (code: string) =>
    [...stockKeys.all(), 'candidates', code] as const,
  holdings: (code: string) => [...stockKeys.all(), 'holdings', code] as const,
  shareholders: (code: string) =>
    [...stockKeys.all(), 'shareholders', code] as const,
  northFlow: (code: string) => [...stockKeys.all(), 'north-flow', code] as const,
  margin: (code: string) => [...stockKeys.all(), 'margin', code] as const,
  revenue: (code: string) => [...stockKeys.all(), 'revenue', code] as const,
} as const;
