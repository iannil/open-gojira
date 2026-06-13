import type { ReactNode } from 'react';
import {
  ArrowUpOutlined,
  ArrowDownOutlined,
  MinusOutlined,
} from '@ant-design/icons';

export interface StatCardDelta {
  /** Display string, e.g. "+12.4%" or "-3.1pp". */
  value: string;
  direction: 'up' | 'down' | 'flat';
  /** Which direction is good. Default 'up'. Use 'down' for metrics where lower is better (e.g. drawdown). */
  good?: 'up' | 'down';
}

export interface StatCardProps {
  /** Short uppercase label, e.g. "年度被动现金流". */
  label: string;
  /** Numeric value (string or node). Rendered with mono font + tabular-nums. */
  value: ReactNode;
  /** Optional delta below value. */
  delta?: StatCardDelta;
  /** Optional tertiary hint below delta, e.g. "目标 ¥120k". */
  hint?: string;
  /** Shows pulsing skeleton instead of value/delta/hint. */
  loading?: boolean;
  /** Makes the whole card clickable. */
  onClick?: () => void;
}

export function StatCard({
  label,
  value,
  delta,
  hint,
  loading,
  onClick,
}: StatCardProps) {
  let deltaTone: 'good' | 'bad' | 'flat' = 'flat';
  let DeltaIcon = MinusOutlined;

  if (delta) {
    if (delta.direction === 'flat') {
      deltaTone = 'flat';
      DeltaIcon = MinusOutlined;
    } else {
      const goodDirection = delta.good ?? 'up';
      const isGood = delta.direction === goodDirection;
      deltaTone = isGood ? 'good' : 'bad';
      DeltaIcon = delta.direction === 'up' ? ArrowUpOutlined : ArrowDownOutlined;
    }
  }

  return (
    <div
      className={`gojira-stat${loading ? ' is-loading' : ''}`}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      style={onClick ? { cursor: 'pointer' } : undefined}
    >
      <div className="gojira-stat-label">{label}</div>
      <div className="gojira-stat-value">{value}</div>
      {delta && !loading && (
        <div className={`gojira-stat-delta gojira-stat-delta--${deltaTone}`}>
          <DeltaIcon style={{ fontSize: 10 }} />
          <span>{delta.value}</span>
        </div>
      )}
      {hint && !loading && <div className="gojira-stat-hint">{hint}</div>}
    </div>
  );
}

export default StatCard;
