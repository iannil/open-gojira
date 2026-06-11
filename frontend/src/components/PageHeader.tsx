import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  enLabel?: string;
  description?: string;
  extra?: ReactNode;
  icon?: ReactNode;
}

export default function PageHeader({
  title,
  subtitle,
  enLabel,
  description,
  extra,
  icon,
}: PageHeaderProps) {
  return (
    <div className="page-header">
      <div className="flex justify-between items-baseline">
        <div>
          <h1>
            {icon && <span className="page-header-icon">{icon}</span>}
            {title}
          </h1>
          {subtitle && (
            <p className="page-header-subtitle">
              {enLabel && <span className="en-label">{enLabel}</span>}
              {subtitle}
            </p>
          )}
          {description && (
            <p className="page-header-desc">{description}</p>
          )}
        </div>
        {extra && <div className="page-header-extra">{extra}</div>}
      </div>
    </div>
  );
}
