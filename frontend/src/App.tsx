import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { App as AntApp, ConfigProvider, theme as antTheme } from 'antd';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';

const CockpitPage = lazy(() => import('./pages/CockpitPage'));
const UniversePage = lazy(() => import('./pages/UniversePage'));
const StrategiesPage = lazy(() => import('./pages/StrategiesPage'));
const PlansPage = lazy(() => import('./pages/PlansPage'));
const CandidatesPage = lazy(() => import('./pages/CandidatesPage'));
const ReviewPage = lazy(() => import('./pages/ReviewPage'));
const StockDetailPage = lazy(() => import('./pages/StockDetailPage'));
const DataManagementPage = lazy(() => import('./pages/DataManagementPage'));
const SchedulerPage = lazy(() => import('./pages/SchedulerPage'));

function LoadingFallback() {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        backgroundColor: '#F5F5F4',
        fontFamily:
          "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      }}
    >
      <div style={{ textAlign: 'center' }}>
        <div
          style={{
            width: 32,
            height: 32,
            border: '3px solid #D6D3D1',
            borderTopColor: '#4F6D93',
            borderRadius: '50%',
            animation: 'spin 0.8s linear infinite',
            margin: '0 auto 16px',
          }}
        />
        <p style={{ fontSize: 14, color: '#78716C', margin: 0 }}>加载中...</p>
        <style>{`
          @keyframes spin {
            to { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    </div>
  );
}

function App() {
  return (
    <ConfigProvider
      theme={{
        algorithm: antTheme.defaultAlgorithm,
        token: {
          colorPrimary: '#4F6D93',
          colorBgContainer: '#FFFFFF',
          colorBgElevated: '#FFFFFF',
          colorBorder: '#D6D3D1',
          colorText: '#1C1917',
          colorTextSecondary: '#57534E',
          borderRadius: 6,
          fontFamily:
            "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        },
      }}
    >
      <ErrorBoundary>
        <AntApp>
          <BrowserRouter>
            <Suspense fallback={<LoadingFallback />}>
            <Routes>
              <Route path="/" element={<Layout />}>
                <Route index element={<CockpitPage />} />
                <Route path="universe" element={<UniversePage />} />
                <Route path="strategies" element={<StrategiesPage />} />
                <Route path="plans" element={<PlansPage />} />
                <Route path="candidates" element={<CandidatesPage />} />
                <Route path="review" element={<ReviewPage />} />
                <Route path="stock/:code" element={<StockDetailPage />} />
                <Route path="data-management" element={<DataManagementPage />} />
                <Route path="scheduler" element={<SchedulerPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Route>
            </Routes>
          </Suspense>
        </BrowserRouter>
        </AntApp>
      </ErrorBoundary>
    </ConfigProvider>
  );
}

export default App;
