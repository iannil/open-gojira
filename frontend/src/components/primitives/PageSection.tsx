import type { ReactNode } from 'react';
import { Card } from 'antd';

export interface PageSectionProps {
  /** Section title. Omit for a content-only section. */
  title?: string;
  /** Optional tertiary subtitle below title. */
  subtitle?: string;
  /** Optional right-aligned action area (e.g. "刷新" / "展开"). */
  extra?: ReactNode;
  /** 'card' wraps in shadowed card; 'plain' renders as titled block. Default 'card'. */
  variant?: 'card' | 'plain';
  children: ReactNode;
}

export function PageSection({
  title,
  subtitle,
  extra,
  variant = 'card',
  children,
}: PageSectionProps) {
  const showHeader = Boolean(title || subtitle || extra);
  const header = showHeader && (
    <div className="gojira-page-section-header">
      <div className="gojira-page-section-title-wrap">
        {title && <h2 className="gojira-page-section-title">{title}</h2>}
        {subtitle && (
          <p className="gojira-page-section-subtitle">{subtitle}</p>
        )}
      </div>
      {extra && <div className="gojira-page-section-extra">{extra}</div>}
    </div>
  );

  if (variant === 'plain') {
    return (
      <section className="gojira-page-section gojira-page-section-plain">
        {header}
        <div className="gojira-page-section-body">{children}</div>
      </section>
    );
  }

  return (
    <section className="gojira-page-section">
      <Card className="gojira-card" bordered={false}>
        {header}
        <div className="gojira-page-section-body">{children}</div>
      </Card>
    </section>
  );
}

export default PageSection;
