export const taskKeys = {
  all: () => ['tasks'] as const,
  list: () => [...taskKeys.all(), 'list'] as const,
  detail: (taskId: string) => [...taskKeys.all(), 'detail', taskId] as const,
  runs: (params?: Record<string, unknown>) =>
    [...taskKeys.all(), 'runs', params] as const,
  health: () => [...taskKeys.all(), 'health'] as const,
} as const;
