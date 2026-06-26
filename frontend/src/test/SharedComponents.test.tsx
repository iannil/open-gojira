/**
 * Component tests for shared UI primitives.
 *
 * Verifies that layout/error/empty-state components render correctly
 * under normal and edge conditions.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { EmptyState } from '../components/primitives';
import { PageHeader } from '../components/primitives';

// ── EmptyState ─────────────────────────────────────────────────────────────

describe('EmptyState', () => {
  it('renders with custom title', () => {
    render(<EmptyState variant="quiet" title="暂无数据" />);
    expect(screen.getByText('暂无数据')).toBeInTheDocument();
  });

  it('renders cold-start variant', () => {
    render(<EmptyState variant="cold" title="首次配置" description="请先配置策略" />);
    expect(screen.getByText('首次配置')).toBeInTheDocument();
    expect(screen.getByText('请先配置策略')).toBeInTheDocument();
  });

  it('renders with custom description (cold variant)', () => {
    render(<EmptyState variant="cold" title="首次配置" description="自定义说明" />);
    expect(screen.getByText('自定义说明')).toBeInTheDocument();
  });
});

// ── PageHeader ──────────────────────────────────────────────────────────────

describe('PageHeader', () => {
  it('renders title and description', () => {
    render(
      <PageHeader
        title="测试页面"
        enLabel="Test"
        purpose="用于测试"
      />,
    );
    expect(screen.getByText('测试页面')).toBeInTheDocument();
    expect(screen.getByText('用于测试')).toBeInTheDocument();
  });
});
