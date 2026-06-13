export const monitoringKeys = {
  all: () => ['monitoring'] as const,
  channels: () => [...monitoringKeys.all(), 'channels'] as const,
  riskRules: () => [...monitoringKeys.all(), 'risk-rules'] as const,
} as const;
