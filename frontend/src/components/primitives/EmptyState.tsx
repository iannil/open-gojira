import type { ReactNode } from 'react';
import { Button } from 'antd';
import {
  InboxOutlined,
  SearchOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';

export type EmptyStateVariant = 'cold' | 'filter' | 'quiet';

export interface EmptyStateCta {
  label: string;
  onClick: () => void;
  /** Default true. Set false for a non-primary (default) button. */
  primary?: boolean;
}

export interface EmptyStateProps {
  /**
   * - cold: never-configured cold start. Requires description; CTA recommended.
   * - filter: has data but no match under current filter. Pair with onClearFilter.
   * - quiet: data exists but no event this period (e.g. no drafts today).
   */
  variant: EmptyStateVariant;
  /** Short headline, e.g. "还没有策略" / "无匹配候选" / "今日无新信号". */
  title: string;
  /** Cold: concept explanation (required). Filter: short hint (optional). Quiet: ignored. */
  description?: string;
  /** Cold variant only. */
  cta?: EmptyStateCta;
  /** Override the default icon for the variant. */
  icon?: ReactNode;
  /** Filter variant only — renders "清除筛选" link button. */
  onClearFilter?: () => void;
}

const DEFAULT_ICONS: Record<EmptyStateVariant, ReactNode> = {
  cold: <InboxOutlined />,
  filter: <SearchOutlined />,
  quiet: <InfoCircleOutlined />,
};

export function EmptyState({
  variant,
  title,
  description,
  cta,
  icon,
  onClearFilter,
}: EmptyStateProps) {
  if (variant === 'cold' && !description) {
    console.warn(
      '<EmptyState variant="cold"> should include a description explaining the concept and next step.',
    );
  }

  return (
    <div
      className={`gojira-empty gojira-empty--${variant}`}
      role="status"
      aria-live="polite"
    >
      <span className="gojira-empty-icon" aria-hidden="true">
        {icon ?? DEFAULT_ICONS[variant]}
      </span>
      <div className="gojira-empty-title">{title}</div>
      {description && variant !== 'quiet' && (
        <div className="gojira-empty-desc">{description}</div>
      )}
      {variant === 'cold' && cta && (
        <Button
          type={cta.primary === false ? 'default' : 'primary'}
          onClick={cta.onClick}
        >
          {cta.label}
        </Button>
      )}
      {variant === 'filter' && onClearFilter && (
        <Button type="link" size="small" onClick={onClearFilter}>
          清除筛选
        </Button>
      )}
    </div>
  );
}

export default EmptyState;
