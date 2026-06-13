import { useMemo } from 'react';
import { Alert, Button, Space, Typography } from 'antd';
import { AlertOutlined, RightOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';

import { useUnresolvedAlertsSummaryQuery } from '../features/alerts';
import type { SystemAlertSeverity } from '../api/types';

const { Text } = Typography;

/**
 * Layout-level banner that surfaces a one-line summary of unresolved
 * system_alerts and links to the full triage UI in MonitoringPage.
 *
 * Visual rules:
 * - 0 alerts        → renders null (zero footprint)
 * - any critical    → red banner with critical / warning breakdown
 * - warnings only   → yellow banner with warning count
 *
 * The expandable detail list that used to live here moved to
 * MonitoringPage's "告警中心" tab; this component is now just a counter
 * + CTA so it stays compact even when there are 50+ alerts.
 */
export function SystemAlertBanner() {
  const q = useUnresolvedAlertsSummaryQuery();
  const navigate = useNavigate();

  const counts = useMemo(() => {
    const list = q.data ?? [];
    const by: Record<SystemAlertSeverity, number> = { critical: 0, warning: 0, info: 0 };
    for (const a of list) by[a.severity] += 1;
    return { ...by, total: list.length };
  }, [q.data]);

  if (counts.total === 0) return null;

  const hasCritical = counts.critical > 0;
  const type: 'error' | 'warning' = hasCritical ? 'error' : 'warning';

  const message = (
    <Space size={12} style={{ width: '100%', justifyContent: 'space-between' }}>
      <Space size={8}>
        <Text strong>
          <span className="num">{counts.total}</span> 个未解决告警
        </Text>
        <Text type="secondary" style={{ fontSize: 'var(--fs-xs)' }}>
          {hasCritical ? (
            <>
              严重 <span className="num" style={{ color: 'var(--red-600)' }}>{counts.critical}</span>
              {' · '}
              警告 <span className="num" style={{ color: 'var(--amber-600)' }}>{counts.warning}</span>
            </>
          ) : (
            <>
              警告 <span className="num" style={{ color: 'var(--amber-600)' }}>{counts.warning}</span>
              {counts.info > 0 && (
                <>
                  {' · '}
                  提示 <span className="num">{counts.info}</span>
                </>
              )}
            </>
          )}
        </Text>
      </Space>
      <Button
        size="small"
        type="link"
        onClick={() => navigate('/monitoring?tab=alerts')}
      >
        查看全部 <RightOutlined />
      </Button>
    </Space>
  );

  return (
    <div style={{ marginBottom: 'var(--sp-3)' }}>
      <Alert
        type={type}
        showIcon
        icon={<AlertOutlined />}
        banner
        message={message}
      />
    </div>
  );
}

export default SystemAlertBanner;
