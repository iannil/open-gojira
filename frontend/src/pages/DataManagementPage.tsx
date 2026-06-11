import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Space, Tabs, Typography } from 'antd';
import { CloudSyncOutlined, RocketOutlined } from '@ant-design/icons';

import PageHeader from '../components/PageHeader';
import { DatabaseOutlined } from '@ant-design/icons';
import { TAB_CONFIG } from '../components/data-management/constants';
import DataHealthDashboard from '../components/data-management/DataHealthDashboard';
import PipelineManagement from '../components/data-management/PipelineManagement';
import StockPoolManagement from '../components/data-management/StockPoolManagement';
import DataQualityPanel from '../components/data-management/DataQualityPanel';
import DataCleanupPanel from '../components/data-management/DataCleanupPanel';
import { fetchUniverseStats, startPipelineRun } from '../api/client';
import type { UniverseCoverageStats } from '../api/types';
import { useAntdStatic } from '../hooks/useAntdStatic';

const { Text } = Typography;

export default function DataManagementPage() {
  const { message } = useAntdStatic();
  const [activeTab, setActiveTab] = useState('health');
  const [refreshKey, setRefreshKey] = useState(0);
  const [stats, setStats] = useState<UniverseCoverageStats | null>(null);
  const [bootstrapping, setBootstrapping] = useState(false);

  useEffect(() => {
    fetchUniverseStats()
      .then(setStats)
      .catch(() => {});
  }, [refreshKey]);

  const triggerRefresh = useCallback(() => {
    setRefreshKey((k) => k + 1);
  }, []);

  const handleBootstrap = useCallback(async () => {
    setBootstrapping(true);
    try {
      await startPipelineRun('universe_bootstrap', {});
      message.success('全量引导已启动，请稍候刷新');
      setTimeout(triggerRefresh, 3000);
    } catch {
      message.error('启动全量引导失败');
    } finally {
      setBootstrapping(false);
    }
  }, [message, triggerRefresh]);

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const handleSyncFromHealth = useCallback((_dataType: string, _runId?: string) => {
    setActiveTab('pipeline');
  }, []);

  const tabItems = TAB_CONFIG.map((tab) => ({
    key: tab.key,
    label: (
      <span>
        {tab.icon} {tab.label}
      </span>
    ),
    children: (
      <div style={{ padding: '0 4px' }}>
        {tab.key === 'health' && (
          <DataHealthDashboard refreshKey={refreshKey} onSync={handleSyncFromHealth} />
        )}
        {tab.key === 'pipeline' && (
          <PipelineManagement onPipelineComplete={triggerRefresh} />
        )}
        {tab.key === 'stockPool' && (
          <StockPoolManagement refreshKey={refreshKey} coverageStats={stats} />
        )}
        {tab.key === 'quality' && (
          <DataQualityPanel refreshKey={refreshKey} />
        )}
        {tab.key === 'cleanup' && (
          <DataCleanupPanel onDataChange={triggerRefresh} />
        )}
      </div>
    ),
  }));

  const isFullCoverage = stats?.mode === 'full_coverage';

  return (
    <div>
      <PageHeader
        title="数据管理"
        enLabel="Data Management"
        icon={<DatabaseOutlined />}
      />

      {stats && (
        <Alert
          type={isFullCoverage ? 'success' : 'info'}
          showIcon
          icon={isFullCoverage ? <CloudSyncOutlined /> : <RocketOutlined />}
          style={{ marginBottom: 16 }}
          message={
            <Space>
              <Text strong>
                {isFullCoverage ? '全量覆盖模式' : '手动模式'}
              </Text>
              <Text type="secondary">
                {stats.total_stocks} 只股票，{stats.valuation_coverage} 只有今日估值（{stats.coverage_pct}%）
              </Text>
            </Space>
          }
          description={
            isFullCoverage
              ? '每日自动同步全 A 股基础数据，策略自动筛选全量股票'
              : '仅同步手动添加的股票数据'
          }
          action={
            !isFullCoverage ? (
              <Button
                size="small"
                type="primary"
                loading={bootstrapping}
                onClick={handleBootstrap}
                icon={<RocketOutlined />}
              >
                启用全量覆盖
              </Button>
            ) : undefined
          }
        />
      )}

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
        size="small"
      />
    </div>
  );
}
