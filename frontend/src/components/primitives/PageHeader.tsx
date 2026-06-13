import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

export interface PageHeaderFlowStep {
  /** Step label, e.g. "策略库" or "运行预案扫描". */
  label: string;
  /** Route to make step clickable. Omit for the current step (highlighted, not clickable). */
  to?: string;
}

export interface PageHeaderProps {
  /** Page title, e.g. "预案". Accepts ReactNode for composite titles (code + name). */
  title: ReactNode;
  /** English label rendered as tracked uppercase secondary, e.g. "Plans". */
  enLabel?: string;
  /** One-sentence business definition. Required — this is the C-pain killer. */
  purpose: string;
  /** Optional typical-flow indicator. Step without `to` is the current step. */
  flow?: PageHeaderFlowStep[];
  /** Optional right-aligned primary actions (e.g. "新建"). */
  actions?: ReactNode;
}

export function PageHeader({
  title,
  enLabel,
  purpose,
  flow,
  actions,
}: PageHeaderProps) {
  return (
    <header className="gojira-page-header">
      <div className="gojira-page-header-title-row">
        <div className="gojira-page-header-title-wrap">
          <h1 className="gojira-page-header-title">{title}</h1>
          {enLabel && (
            <span className="gojira-page-header-en">{enLabel}</span>
          )}
        </div>
        {actions && (
          <div className="gojira-page-header-actions">{actions}</div>
        )}
      </div>
      <p className="gojira-page-header-purpose">{purpose}</p>
      {flow && flow.length > 0 && (
        <nav className="gojira-page-header-flow" aria-label="典型流程">
          {flow.map((step, idx) => {
            const isCurrent = !step.to;
            return (
              <span
                key={idx}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 'var(--sp-2)',
                }}
              >
                {step.to ? (
                  <Link
                    to={step.to}
                    className={`gojira-flow-step${isCurrent ? ' is-current' : ''}`}
                  >
                    {step.label}
                  </Link>
                ) : (
                  <span
                    className={`gojira-flow-step${isCurrent ? ' is-current' : ''}`}
                    aria-current="step"
                  >
                    {step.label}
                  </span>
                )}
                {idx < flow.length - 1 && (
                  <span className="gojira-flow-sep" aria-hidden="true">
                    →
                  </span>
                )}
              </span>
            );
          })}
        </nav>
      )}
    </header>
  );
}

export default PageHeader;
