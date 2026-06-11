import { Component, type ErrorInfo, type ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
  detailsOpen: boolean;
}

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      detailsOpen: false,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    this.setState({ errorInfo });
    console.error('[ErrorBoundary] Caught error:', error, errorInfo);
  }

  handleRetry = (): void => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      detailsOpen: false,
    });
  };

  toggleDetails = (): void => {
    this.setState((prev) => ({ detailsOpen: !prev.detailsOpen }));
  };

  render(): ReactNode {
    if (!this.state.hasError) {
      return this.props.children;
    }

    const { error, errorInfo, detailsOpen } = this.state;

    return (
      <div style={styles.container}>
        <div style={styles.card}>
          {/* Icon */}
          <div style={styles.iconWrapper}>
            <svg
              width="48"
              height="48"
              viewBox="0 0 48 48"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <circle cx="24" cy="24" r="22" stroke="#4F6D93" strokeWidth="2.5" fill="none" />
              <path
                d="M24 14v14"
                stroke="#4F6D93"
                strokeWidth="2.5"
                strokeLinecap="round"
              />
              <circle cx="24" cy="34" r="1.8" fill="#4F6D93" />
            </svg>
          </div>

          {/* Message */}
          <h2 style={styles.title}>
            页面加载出错
          </h2>
          <p style={styles.description}>
            抱歉，页面在加载过程中遇到了问题。请尝试刷新页面，如果问题持续存在，请联系管理员。
          </p>

          {/* Retry button */}
          <button onClick={this.handleRetry} style={styles.retryButton}>
            重新加载
          </button>

          {/* Collapsible error details */}
          <button onClick={this.toggleDetails} style={styles.detailsToggle}>
            {detailsOpen ? '收起错误详情 ▲' : '查看错误详情 ▼'}
          </button>

          {detailsOpen && (
            <div style={styles.detailsBox}>
              <p style={styles.detailsLabel}>错误信息：</p>
              <pre style={styles.detailsContent}>
                {error?.toString()}
              </pre>
              {errorInfo?.componentStack && (
                <>
                  <p style={{ ...styles.detailsLabel, marginTop: 12 }}>
                    组件堆栈：
                  </p>
                  <pre style={styles.detailsContent}>
                    {errorInfo.componentStack}
                  </pre>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    );
  }
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: '100vh',
    backgroundColor: '#F5F5F4',
    fontFamily:
      "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 8,
    border: '1px solid #D6D3D1',
    padding: '40px 48px',
    maxWidth: 520,
    width: '90%',
    textAlign: 'center' as const,
    boxShadow: '0 1px 3px rgba(0, 0, 0, 0.06)',
  },
  iconWrapper: {
    marginBottom: 20,
  },
  title: {
    fontSize: 20,
    fontWeight: 600,
    color: '#1C1917',
    margin: '0 0 8px 0',
  },
  description: {
    fontSize: 14,
    color: '#57534E',
    lineHeight: 1.6,
    margin: '0 0 24px 0',
  },
  retryButton: {
    display: 'inline-block',
    padding: '10px 32px',
    fontSize: 14,
    fontWeight: 500,
    color: '#FFFFFF',
    backgroundColor: '#4F6D93',
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    transition: 'background-color 0.2s',
  },
  detailsToggle: {
    display: 'block',
    margin: '20px auto 0',
    padding: '4px 8px',
    fontSize: 12,
    color: '#78716C',
    backgroundColor: 'transparent',
    border: 'none',
    cursor: 'pointer',
    transition: 'color 0.2s',
  },
  detailsBox: {
    marginTop: 16,
    padding: 16,
    backgroundColor: '#FAFAF9',
    borderRadius: 6,
    border: '1px solid #E7E5E4',
    textAlign: 'left' as const,
  },
  detailsLabel: {
    fontSize: 12,
    fontWeight: 600,
    color: '#57534E',
    margin: '0 0 4px 0',
  },
  detailsContent: {
    fontSize: 12,
    color: '#B93530',
    backgroundColor: '#FDE8E7',
    padding: 12,
    borderRadius: 4,
    margin: '0 0 0 0',
    whiteSpace: 'pre-wrap' as const,
    wordBreak: 'break-word' as const,
    maxHeight: 200,
    overflowY: 'auto' as const,
  },
};

export default ErrorBoundary;
