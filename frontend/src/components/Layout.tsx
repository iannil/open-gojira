import { useState, useRef, useEffect, useCallback, type ReactNode } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import {
  DashboardOutlined,
  AppstoreOutlined,
  DatabaseOutlined,
  TransactionOutlined,
  BellOutlined,
  FileTextOutlined,
  CheckCircleOutlined,
  PieChartOutlined,
  DollarOutlined,
  PercentageOutlined,
  AuditOutlined,
  LineChartOutlined,
  BankOutlined,
  StockOutlined,
  EditOutlined,
  DownOutlined,
  ExperimentOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';

import { SystemAlertBanner } from './SystemAlertBanner';

type NavItem = { key: string; label: string; labelEn: string; icon: ReactNode };
type NavGroup = {
  label: string;
  type: 'flat' | 'dropdown';
  items: NavItem[];
};

const NAV_GROUPS: NavGroup[] = [
  {
    label: '入口',
    type: 'flat',
    items: [
      { key: '/', label: '主看板', labelEn: 'Cockpit', icon: <DashboardOutlined /> },
    ],
  },
  {
    label: '选股深研',
    type: 'dropdown',
    items: [
      { key: '/universe', label: '股票池', labelEn: 'Stock Pool', icon: <AppstoreOutlined /> },
      { key: '/engine', label: '双引擎', labelEn: 'Engine', icon: <ExperimentOutlined /> },
      { key: '/reports', label: '研究报告', labelEn: 'Reports', icon: <FileTextOutlined /> },
    ],
  },
  {
    label: '交易执行',
    type: 'flat',
    items: [
      { key: '/drafts', label: '草稿', labelEn: 'Drafts', icon: <EditOutlined /> },
      { key: '/trades', label: '成交流水', labelEn: 'Trades', icon: <TransactionOutlined /> },
    ],
  },
  {
    label: '持仓分析',
    type: 'dropdown',
    items: [
      { key: '/portfolio', label: '持仓组合', labelEn: 'Portfolio', icon: <PieChartOutlined /> },
      { key: '/dividend', label: '股息红利', labelEn: 'Dividends', icon: <DollarOutlined /> },
      { key: '/valuation', label: '估值分析', labelEn: 'Valuation', icon: <StockOutlined /> },
    ],
  },
  {
    label: '系统管理',
    type: 'dropdown',
    items: [
      { key: '/market', label: '市场指数', labelEn: 'Market', icon: <LineChartOutlined /> },
      { key: '/fee-configs', label: '券商费率', labelEn: 'Fees', icon: <PercentageOutlined /> },
      { key: '/corp-actions', label: '公司行动', labelEn: 'Corp Actions', icon: <BankOutlined /> },
      { key: '/data-management', label: '数据管理', labelEn: 'Data', icon: <DatabaseOutlined /> },
      { key: '/task-center', label: '任务管理', labelEn: 'Task Center', icon: <ThunderboltOutlined /> },
      { key: '/monitoring', label: '监控告警', labelEn: 'Monitoring', icon: <BellOutlined /> },
      { key: '/audit-log', label: '审计日志', labelEn: 'Audit Log', icon: <AuditOutlined /> },
    ],
  },
  {
    label: '质量评估',
    type: 'flat',
    items: [
      { key: '/eval', label: 'Eval Set', labelEn: 'LLM Baseline', icon: <CheckCircleOutlined /> },
    ],
  },
];

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const activeKey = '/' + (location.pathname.split('/')[1] || '');

  const [openDropdown, setOpenDropdown] = useState<string | null>(null);
  const dropdownRefs = useRef<Record<string, HTMLDivElement | null>>({});

  /* 点击外部关闭下拉菜单 */
  const handleClickOutside = useCallback(
    (e: MouseEvent) => {
      if (!openDropdown) return;
      const el = dropdownRefs.current[openDropdown];
      if (el && !el.contains(e.target as Node)) {
        setOpenDropdown(null);
      }
    },
    [openDropdown],
  );

  useEffect(() => {
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [handleClickOutside]);

  const toggleDropdown = (label: string) => {
    setOpenDropdown((prev) => (prev === label ? null : label));
  };

  const handleNavClick = (key: string) => {
    setOpenDropdown(null);
    navigate(key);
  };

  const isGroupActive = (items: NavItem[]) =>
    items.some((item) => activeKey === item.key);

  return (
    <div className="app-shell">
      <header className="topnav" role="navigation" aria-label="主导航">
        <div className="topnav-brand">
          <span className="topnav-brand-name">Open Gojira</span>
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

              {group.type === 'dropdown' ? (
                /* ── 下拉式二级菜单 ──────────────────────────────── */
                <div
                  className={`topnav-dropdown ${isGroupActive(group.items) ? 'active' : ''}`}
                  ref={(el) => {
                    dropdownRefs.current[group.label] = el;
                  }}
                >
                  <button
                    type="button"
                    className={`topnav-dropdown-trigger ${openDropdown === group.label ? 'open' : ''}`}
                    onClick={() => toggleDropdown(group.label)}
                    aria-haspopup="true"
                    aria-expanded={openDropdown === group.label}
                    aria-label={`${group.label} 菜单`}
                  >
                    <span className="topnav-dropdown-trigger-label">{group.label}</span>
                    <DownOutlined
                      className={`topnav-dropdown-caret ${openDropdown === group.label ? 'open' : ''}`}
                    />
                  </button>

                  {openDropdown === group.label && (
                    <div className="topnav-dropdown-menu" role="menu">
                      {group.items.map((item) => (
                        <button
                          key={item.key}
                          type="button"
                          className={`topnav-dropdown-item ${activeKey === item.key ? 'active' : ''}`}
                          onClick={() => handleNavClick(item.key)}
                          role="menuitem"
                          aria-current={activeKey === item.key ? 'page' : undefined}
                        >
                          <span className="topnav-dropdown-item-icon" aria-hidden="true">
                            {item.icon}
                          </span>
                          <span className="topnav-dropdown-item-label">{item.label}</span>
                          <span className="topnav-dropdown-item-label-en">{item.labelEn}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                /* ── 扁平按钮（原逻辑） ─────────────────────────── */
                group.items.map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    className={`topnav-item ${activeKey === item.key ? 'active' : ''}`}
                    onClick={() => handleNavClick(item.key)}
                    aria-current={activeKey === item.key ? 'page' : undefined}
                    aria-label={`${group.label} · ${item.label} ${item.labelEn}`}
                    title={`${group.label} · ${item.label} ${item.labelEn}`}
                  >
                    <span className="topnav-item-icon" aria-hidden="true">
                      {item.icon}
                    </span>
                    <span className="topnav-item-label">{item.label}</span>
                  </button>
                ))
              )}
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
