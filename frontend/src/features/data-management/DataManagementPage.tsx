import { useState } from 'react';
import { Alert, Button, Space, Tabs, Typography } from 'antd';
import { CloudSyncOutlined, DatabaseOutlined, RocketOutlined } from '@ant-design/icons';

import { PageHeader } from '../../components/primitives';
import { useAntdStatic } from '../../hooks/useAntdStatic';
import { startPipelineRun } from '../../api/client';
import { useUniverseStatsQuery } from './useDataQueries';
import { useStartPipelineRunMutation } from './useDataMutations';
import { TAB_CONFIG } from './constants';
import DataHealthDashboard from './components/DataHealthDashboard';
import PipelineManagement from './components/PipelineManagement';
import StockPoolManagement from './components/StockPoolManagement';
import DataQualityPanel from './components/DataQualityPanel';
import DataCleanupPanel from './components/DataCleanupPanel';

const { Text } = Typography;

export default function DataManagementPage() {
  const { message } = useAntdStatic();
  const [activeTab, setActiveTab] = useState('health');
  const [bootstrapping, setBootstrapping] = useState(false);

  const statsQ = useUniverseStatsQuery();
  const stats = statsQ.data;
  const isFullCoverage = stats?.mode === 'full_coverage';

  const bootstrapM = useStartPipelineRunMutation();

  const handleBootstrap = async () => {
    setBootstrapping(true);
    try {
      await startPipelineRun('universe_bootstrap', {});
      message.success('全量引导已启动，请稍候刷新');
    } catch {
      message.error('启动全量引导失败');
    } finally {
      setBootstrapping(false);
    }
  };

  const handleSyncFromHealth = () => {
    setActiveTab('pipeline');
  };

  const tabItems = TAB_CONFIG.map((tab) => ({
    key: tab.key,
    label: (
      <span>
        {tab.icon} {tab.label}
      </span>
    ),
    children: (
      <div style={{ padding: '0 4px' }}>
        {tab.key === 'health' && <DataHealthDashboard onSync={handleSyncFromHealth} />}
        {tab.key === 'pipeline' && <PipelineManagement />}
        {tab.key === 'stockPool' && <StockPoolManagement coverageStats={stats ?? null} />}
        {tab.key === 'quality' && <DataQualityPanel />}
        {tab.key === 'cleanup' && <DataCleanupPanel />}
      </div>
    ),
  }));

  return (
    <div>
      <PageHeader
        title="数据管理"
        enLabel="Data"
        purpose="管理 A 股数据的同步、健康、质量、清理。是策略和预案运行的输入基座 —— 数据不准，下游全错。"
        flow={[
          { label: '数据管理' },
          { to: '/strategies', label: '策略库' },
          { to: '/plans', label: '预案' },
        ]}
      />

      {stats && (
        <Alert
          type={isFullCoverage ? 'success' : 'info'}
          showIcon
          icon={isFullCoverage ? <CloudSyncOutlined /> : <RocketOutlined />}
          style={{ marginBottom: 'var(--sp-4)' }}
          message={
            <Space>
              <Text strong>{isFullCoverage ? '全量覆盖模式' : '手动模式'}</Text>
              <Text type="secondary">
                <span className="num">{stats.total_stocks}</span> 只股票，
                <span className="num">{stats.valuation_coverage}</span> 只有今日估值（
                <span className="num">{stats.coverage_pct}%</span>）
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
                loading={bootstrapping || bootstrapM.isPending}
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

// Re-export icon for backward compat (Layout imports)
export { DatabaseOutlined };
