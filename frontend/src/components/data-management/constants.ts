import {
  CloudSyncOutlined,
  DashboardOutlined,
  DeleteOutlined,
  AppstoreOutlined,
  SafetyCertificateOutlined,
  LineChartOutlined,
  FundOutlined,
  DollarOutlined,
  PartitionOutlined,
} from '@ant-design/icons';
import React from 'react';

export const DATA_TYPES = ['valuations', 'financials', 'klines', 'dividends'] as const;
export type DataTypeKey = (typeof DATA_TYPES)[number];

export const DATA_TYPE_LABELS: Record<DataTypeKey, string> = {
  valuations: '估值快照',
  financials: '财报数据',
  klines: 'K线数据',
  dividends: '分红数据',
};

export const DATA_TYPE_ICONS: Record<DataTypeKey, React.ReactNode> = {
  valuations: React.createElement(LineChartOutlined),
  financials: React.createElement(FundOutlined),
  klines: React.createElement(PartitionOutlined),
  dividends: React.createElement(DollarOutlined),
};

export const DATA_TYPE_COLORS: Record<DataTypeKey, string> = {
  valuations: '#1890ff',
  financials: '#52c41a',
  klines: '#faad14',
  dividends: '#722ed1',
};

export const FRESHNESS_LABELS: Record<string, string> = {
  fresh: '新鲜',
  stale: '陈旧',
  missing: '缺失',
};

export const FRESHNESS_COLORS: Record<string, string> = {
  fresh: '#52c41a',
  stale: '#faad14',
  missing: '#ff4d4f',
};

export const PIPELINE_STATUS_COLORS: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  completed: 'success',
  completed_with_errors: 'warning',
  failed: 'error',
  cancelled: 'default',
};

export const PIPELINE_STATUS_LABELS: Record<string, string> = {
  pending: '等待中',
  running: '运行中',
  completed: '已完成',
  completed_with_errors: '部分失败',
  failed: '失败',
  cancelled: '已取消',
};

export const TAB_CONFIG = [
  { key: 'health', label: '数据健康概览', icon: React.createElement(DashboardOutlined) },
  { key: 'pipeline', label: '数据同步', icon: React.createElement(CloudSyncOutlined) },
  { key: 'stockPool', label: '股票池管理', icon: React.createElement(AppstoreOutlined) },
  { key: 'quality', label: '数据质量', icon: React.createElement(SafetyCertificateOutlined) },
  { key: 'cleanup', label: '数据清理', icon: React.createElement(DeleteOutlined) },
] as const;

export const POLL_INTERVAL_MS = 3000;
