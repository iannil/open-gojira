import type { ReactNode } from 'react';
import { Button } from 'antd';

export interface FilterBarProps {
  /** Filter controls (Select / DatePicker / Input etc). */
  children: ReactNode;
  /** Renders "重置" link button when provided. */
  onReset?: () => void;
  /** Right-aligned custom actions (e.g. "导出"). */
  actions?: ReactNode;
}

export function FilterBar({ children, onReset, actions }: FilterBarProps) {
  return (
    <div className="gojira-filter-bar">
      <div className="gojira-filter-bar-controls">{children}</div>
      {(onReset || actions) && (
        <div className="gojira-filter-bar-actions">
          {onReset && (
            <Button type="text" size="small" onClick={onReset}>
              重置
            </Button>
          )}
          {actions}
        </div>
      )}
    </div>
  );
}

export default FilterBar;
