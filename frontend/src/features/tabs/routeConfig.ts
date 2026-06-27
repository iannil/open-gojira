import { lazy, type ComponentType, type LazyExoticComponent } from 'react';

/* ── Lazy-loaded page components ──────────────────────────────────── */

export const CockpitPage = lazy(() => import('../cockpit/CockpitPage'));
export const PortfolioPage = lazy(() => import('../portfolio/PortfolioPage'));
export const DividendPage = lazy(() => import('../dividend/DividendPage'));
export const FeeConfigsPage = lazy(() => import('../fee-configs/FeeConfigsPage'));
export const AuditLogPage = lazy(() => import('../audit-log/AuditLogPage'));
export const MarketPage = lazy(() => import('../market/MarketPage'));
export const CorpActionsPage = lazy(() => import('../corp-actions/CorpActionsPage'));
export const ValuationPage = lazy(() => import('../valuation/ValuationPage'));
export const UniversePage = lazy(() => import('../universe/UniversePage'));
export const TradesPage = lazy(() => import('../trades/TradesPage'));
export const StockDetailPage = lazy(() => import('../stock-detail/StockDetailPage'));
export const DataManagementPage = lazy(() => import('../data-management/DataManagementPage'));
export const SchedulerPage = lazy(() => import('../scheduler/SchedulerPage'));
export const MonitoringPage = lazy(() => import('../monitoring/MonitoringPage'));
export const EvalPage = lazy(() => import('../eval/EvalSetPage'));
export const DraftsPage = lazy(() => import('../drafts/DraftsPage'));
export const ReportsPage = lazy(() => import('../reports/ReportsPage'));
export const EnginePage = lazy(() => import('../engine/EnginePage'));
export const TaskCenterPage = lazy(() => import('../task-center/TaskCenterPage'));

/* ── Route definition type ────────────────────────────────────────── */

export interface RouteDef {
  path: string;
  title: string;
  titleEn: string;
  component: LazyExoticComponent<ComponentType<any>>;
  /** Whether this route uses route params (dynamic segment like :code) */
  dynamic?: boolean;
  /** Extract a display title from path params */
  tabTitle?: (pathname: string) => string;
}

/* ── Route config (canonical source of truth) ─────────────────────── */

export const ROUTE_CONFIG: RouteDef[] = [
  {
    path: '/',
    title: '主看板',
    titleEn: 'Cockpit',
    component: CockpitPage,
  },
  {
    path: '/universe',
    title: '股票池',
    titleEn: 'Stock Pool',
    component: UniversePage,
  },
  {
    path: '/engine',
    title: '双引擎',
    titleEn: 'Engine',
    component: EnginePage,
  },
  {
    path: '/reports',
    title: '研究报告',
    titleEn: 'Reports',
    component: ReportsPage,
  },
  {
    path: '/drafts',
    title: '草稿',
    titleEn: 'Drafts',
    component: DraftsPage,
  },
  {
    path: '/trades',
    title: '成交流水',
    titleEn: 'Trades',
    component: TradesPage,
  },
  {
    path: '/portfolio',
    title: '持仓组合',
    titleEn: 'Portfolio',
    component: PortfolioPage,
  },
  {
    path: '/dividend',
    title: '股息红利',
    titleEn: 'Dividends',
    component: DividendPage,
  },
  {
    path: '/valuation',
    title: '估值分析',
    titleEn: 'Valuation',
    component: ValuationPage,
  },
  {
    path: '/market',
    title: '市场指数',
    titleEn: 'Market',
    component: MarketPage,
  },
  {
    path: '/fee-configs',
    title: '券商费率',
    titleEn: 'Fees',
    component: FeeConfigsPage,
  },
  {
    path: '/corp-actions',
    title: '公司行动',
    titleEn: 'Corp Actions',
    component: CorpActionsPage,
  },
  {
    path: '/data-management',
    title: '数据管理',
    titleEn: 'Data',
    component: DataManagementPage,
  },
  {
    path: '/scheduler',
    title: '调度器',
    titleEn: 'Scheduler',
    component: SchedulerPage,
  },
  {
    path: '/task-center',
    title: '任务管理',
    titleEn: 'Task Center',
    component: TaskCenterPage,
  },
  {
    path: '/monitoring',
    title: '监控告警',
    titleEn: 'Monitoring',
    component: MonitoringPage,
  },
  {
    path: '/audit-log',
    title: '审计日志',
    titleEn: 'Audit Log',
    component: AuditLogPage,
  },
  {
    path: '/eval',
    title: 'Eval Set',
    titleEn: 'LLM Baseline',
    component: EvalPage,
  },
  {
    path: '/stock/:code',
    title: '股票详情',
    titleEn: 'Stock Detail',
    component: StockDetailPage,
    dynamic: true,
    tabTitle: (pathname: string) => {
      const match = pathname.match(/^\/stock\/(.+)$/);
      return match ? `股票 ${match[1]}` : '股票详情';
    },
  },
];

/* ── Lookup helpers ───────────────────────────────────────────────── */

/** Find a route def by its path pattern (static match or dynamic prefix). */
export function findRouteDef(pathname: string): RouteDef | undefined {
  return ROUTE_CONFIG.find((r) => {
    if (!r.dynamic) return r.path === pathname;
    const staticPart = r.path.split(':')[0];
    return pathname.startsWith(staticPart);
  });
}

/** Resolve the display title for a given pathname. */
export function resolveTabTitle(pathname: string, routeDef?: RouteDef): string {
  const route = routeDef ?? findRouteDef(pathname);
  if (!route) return pathname;
  if (route.tabTitle) return route.tabTitle(pathname);
  return route.title;
}
