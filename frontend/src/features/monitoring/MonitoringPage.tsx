import { Tabs } from 'antd';
import {
  BarChartOutlined,
  BellOutlined,
  SafetyCertificateOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { useSearchParams } from 'react-router-dom';

import { PageHeader } from '../../components/primitives';
import ChannelsTab from './components/ChannelsTab';
import MetricsTab from './components/MetricsTab';
import RiskRulesTab from './components/RiskRulesTab';
import { AlertsTab } from '../alerts';

const VALID_TABS = ['metrics', 'channels', 'risk_rules', 'alerts'] as const;
type TabKey = (typeof VALID_TABS)[number];

export default function MonitoringPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabFromUrl = searchParams.get('tab');
  const activeTab: TabKey =
    tabFromUrl && (VALID_TABS as readonly string[]).includes(tabFromUrl)
      ? (tabFromUrl as TabKey)
      : 'channels';

  const handleTabChange = (key: string) => {
    const next = new URLSearchParams(searchParams);
    if (key === 'channels') next.delete('tab');
    else next.set('tab', key);
    setSearchParams(next, { replace: true });
  };

  return (
    <div>
      <PageHeader
        title="监控配置"
        enLabel="Monitoring"
        purpose="止损止盈规则 + 通知通道 + 告警中心。规则由 scheduler 每 5 分钟评估；告警按级别过滤分发到通道；告警中心看历史 + 批量处理。"
        flow={[{ label: '监控配置' }]}
      />

      <Tabs
        activeKey={activeTab}
        onChange={handleTabChange}
        items={[
          {
            key: 'metrics',
            label: (
              <span>
                <BarChartOutlined /> 运营度量
              </span>
            ),
            children: <MetricsTab />,
          },
          {
            key: 'channels',
            label: (
              <span>
                <BellOutlined /> 通知通道
              </span>
            ),
            children: <ChannelsTab />,
          },
          {
            key: 'risk_rules',
            label: (
              <span>
                <SafetyCertificateOutlined /> 止损止盈规则
              </span>
            ),
            children: <RiskRulesTab />,
          },
          {
            key: 'alerts',
            label: (
              <span>
                <WarningOutlined /> 告警中心
              </span>
            ),
            children: <AlertsTab />,
          },
        ]}
      />
    </div>
  );
}
