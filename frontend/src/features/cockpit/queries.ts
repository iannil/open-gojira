export const cockpitKeys = {
  all: () => ['cockpit'] as const,
  summary: () => [...cockpitKeys.all(), 'summary'] as const,
  themeExposure: () => [...cockpitKeys.all(), 'theme-exposure'] as const,
  cashflowGoal: () => [...cockpitKeys.all(), 'cashflow-goal'] as const,
  criticalAlerts: () => [...cockpitKeys.all(), 'critical-alerts'] as const,
} as const;
