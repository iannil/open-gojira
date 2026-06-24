import type { ReactNode } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import {
  DashboardOutlined,
  AppstoreOutlined,
  DatabaseOutlined,
  ClockCircleOutlined,
  TransactionOutlined,
  BellOutlined,
  FileTextOutlined,
} from '@ant-design/icons';

import { SystemAlertBanner } from './SystemAlertBanner';

const NAV_GROUPS: Array<{
  label: string;
  items: Array<{ key: string; label: string; labelEn: string; icon: ReactNode }>;
}> = [
  {
    label: '入口',
    items: [
      { key: '/', label: '主看板', labelEn: 'Cockpit', icon: <DashboardOutlined /> },
    ],
  },
  {
    label: '数据',
    items: [
      { key: '/universe', label: '股票池', labelEn: 'Stock Pool', icon: <AppstoreOutlined /> },
      { key: '/data-management', label: '数据管理', labelEn: 'Data', icon: <DatabaseOutlined /> },
    ],
  },
  {
    label: '执行',
    items: [
      { key: '/drafts', label: '草稿', labelEn: 'Drafts', icon: <FileTextOutlined /> },
      { key: '/trades', label: '成交流水', labelEn: 'Trades', icon: <TransactionOutlined /> },
    ],
  },
  {
    label: '自动化',
    items: [
      { key: '/scheduler', label: '定时任务', labelEn: 'Scheduler', icon: <ClockCircleOutlined /> },
      { key: '/monitoring', label: '监控配置', labelEn: 'Monitoring', icon: <BellOutlined /> },
    ],
  },
];

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const activeKey = '/' + (location.pathname.split('/')[1] || '');

  return (
    <div className="app-shell">
      <header className="topnav" role="navigation" aria-label="主导航">
        <div className="topnav-brand">
          <span className="topnav-brand-name">Gojira</span>
          <span className="topnav-brand-tagline">自动驾驶舱 v2</span>
        </div>

        <nav className="topnav-nav" aria-label="功能导航">
          {NAV_GROUPS.map((group, idx) => (
            <span
              key={group.label}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
            >
              {idx > 0 && (
                <span
                  aria-hidden="true"
                  style={{
                    width: 1,
                    height: 18,
                    background: '#D6D3D1',
                    margin: '0 6px',
                  }}
                />
              )}
              {group.items.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={`topnav-item ${activeKey === item.key ? 'active' : ''}`}
                  onClick={() => navigate(item.key)}
                  aria-current={activeKey === item.key ? 'page' : undefined}
                  aria-label={`${group.label} · ${item.label} ${item.labelEn}`}
                  title={`${group.label} · ${item.label} ${item.labelEn}`}
                >
                  <span className="topnav-item-icon" aria-hidden="true">
                    {item.icon}
                  </span>
                  <span className="topnav-item-label">{item.label}</span>
                </button>
              ))}
            </span>
          ))}
        </nav>

        <div className="topnav-version">v2.0</div>
      </header>

      <main className="main-content">
        <SystemAlertBanner />
        <Outlet />
      </main>
    </div>
  );
}
