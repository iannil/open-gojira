export const schedulerKeys = {
  all: () => ['scheduler'] as const,
  jobs: () => [...schedulerKeys.all(), 'jobs'] as const,
  executions: (limit: number) =>
    [...schedulerKeys.all(), 'executions', limit] as const,
} as const;
