import { strategyKeys } from '../strategies/queries';

export const planKeys = {
  all: () => ['plans'] as const,
} as const;

/** Strategies key is owned by the strategies feature. Re-exported here so
 * existing plan mutations that need to invalidate strategies stay terse. */
export { strategyKeys };
