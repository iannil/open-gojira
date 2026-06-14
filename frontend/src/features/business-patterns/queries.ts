export const businessPatternKeys = {
  all: () => ['business-patterns'] as const,
  detail: (id: number) => ['business-patterns', id] as const,
  thesisTemplates: (id: number) =>
    ['business-patterns', id, 'thesis-templates'] as const,
} as const;
