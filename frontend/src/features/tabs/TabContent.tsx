import { Suspense } from 'react';
import { Route, Routes, Outlet, Navigate } from 'react-router-dom';
import { useTabs } from './TabContext';
import { ROUTE_CONFIG } from './routeConfig';

/* ── Loading fallback ─────────────────────────────────────────────── */

function TabLoading() {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 48,
        color: '#78716C',
        fontSize: 14,
      }}
    >
      加载中...
    </div>
  );
}

/* ── Build a <Routes> block that matches a given pathname ────────── */

function RoutesForLocation({ pathname }: { pathname: string }) {
  return (
    <Routes location={pathname}>
      {ROUTE_CONFIG.map((route) => {
        // For the root path, use path="/"
        // For other paths, use absolute paths
        const routePath = route.path === '/' ? '/' : route.path;
        return (
          <Route
            key={route.path}
            path={routePath}
            element={
              <Suspense fallback={<TabLoading />}>
                <route.component />
              </Suspense>
            }
          />
        );
      })}
      {/* Catch-all: redirect to root */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

/* ── TabContent: renders all open tabs with keep-alive ───────────── */

export default function TabContent() {
  const { tabs, activeKey } = useTabs();

  return (
    <>
      {/* Active tab — rendered via normal React Router Outlet */}
      <div
        className="tab-content-panel tab-content-panel--active"
        aria-hidden={false}
      >
        <Suspense fallback={<TabLoading />}>
          <Outlet />
        </Suspense>
      </div>

      {/* Inactive tabs — rendered with their own Routes context for keep-alive */}
      {tabs
        .filter((tab) => tab.key !== activeKey)
        .map((tab) => (
          <div
            key={tab.key}
            className="tab-content-panel"
            aria-hidden={true}
            style={{ display: 'none' }}
          >
            <Suspense fallback={<TabLoading />}>
              <RoutesForLocation pathname={tab.pathname} />
            </Suspense>
          </div>
        ))}
    </>
  );
}
