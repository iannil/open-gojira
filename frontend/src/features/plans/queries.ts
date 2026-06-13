export const planKeys = {
  all: () => ['plans'] as const,
} as const;

// Shared read-only dictionary (strategy name lookups). Referenced as a flat
// ['strategies'] key; lift to its own feature module when a 2nd consumer appears.
export const strategiesKey = () => ['strategies'] as const;
