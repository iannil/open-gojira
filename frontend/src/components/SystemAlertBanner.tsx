import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Collapse,
  Popconfirm,
  Space,
  Tag,
  Typography,
} from 'antd';
import {
  AlertOutlined,
  CheckCircleOutlined,
  DownOutlined,
  ReloadOutlined,
  UpOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';

import { listSystemAlerts, resolveSystemAlert } from '../api/client';
import type { SystemAlert, SystemAlertCategory, SystemAlertSeverity } from '../api/types';
import { useAntdStatic } from '../hooks/useAntdStatic';

const { Text, Paragraph } = Typography;

const severityColor: Record<SystemAlertSeverity, 'error' | 'warning' | 'info'> = {
  critical: 'error',
  warning: 'warning',
  info: 'info',
};

const severityLabel: Record<SystemAlertSeverity, string> = {
  critical: '严重',
  warning: '警告',
  info: '提示',
};

const categoryLabel: Record<SystemAlertCategory, string> = {
  data: '数据',
  scheduler: '调度',
  api: 'API',
  db: '数据库',
  token: 'Token',
};

const POLL_INTERVAL_MS = 60_000;

/**
 * Cockpit-wide banner that surfaces infrastructure-level alerts from
 * system_alerts (data stale / API failures / scheduler crashes / token
 * issues / DB corruption). Mounted in Layout so every page sees it.
 *
 * Visibility:
 * - critical present  → red banner with count, expandable to detail list
 * - warnings only     → yellow banner with count, expandable
 * - info only         → no top banner, but still appears in expanded list
 * - no alerts at all  → renders null (zero footprint)
 */
export function SystemAlertBanner() {
  const [alerts, setAlerts] = useState<SystemAlert[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);
  const { message } = useAntdStatic();

  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    try {
      const list = await listSystemAlerts({ unresolved_only: true, limit: 50 });
      setAlerts(list);
    } catch {
      // Silent: a transient API failure should not block the UI.
      // The next 60s poll will retry automatically.
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAlerts();
    const id = window.setInterval(fetchAlerts, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [fetchAlerts]);

  const criticalCount = alerts.filter((a) => a.severity === 'critical').length;
  const warningCount = alerts.filter((a) => a.severity === 'warning').length;

  const handleResolve = async (id: number) => {
    try {
      await resolveSystemAlert(id);
      message.success('已标记为已解决');
      await fetchAlerts();
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        '解决失败';
      message.error(detail);
    }
  };

  // No unresolved alerts → render nothing (zero footprint on healthy systems)
  if (alerts.length === 0) {
    return null;
  }

  const hasCriticalBanner = criticalCount > 0;
  const hasWarningBanner = criticalCount === 0 && warningCount > 0;

  return (
    <div style={{ marginBottom: 16 }}>
      {hasCriticalBanner && (
        <Alert
          type="error"
          showIcon
          icon={<AlertOutlined />}
          banner
          message={
            <Space>
              <Text strong>{criticalCount} 个严重告警</Text>
              {warningCount > 0 && (
                <Text type="secondary">+ {warningCount} 个警告</Text>
              )}
              <Button
                size="small"
                type="link"
                onClick={() => setExpanded((v) => !v)}
              >
                {expanded ? '收起' : '展开详情'}
                {expanded ? <UpOutlined /> : <DownOutlined />}
              </Button>
              <Button
                size="small"
                type="link"
                onClick={fetchAlerts}
                loading={loading}
                icon={<ReloadOutlined />}
              >
                刷新
              </Button>
            </Space>
          }
        />
      )}

      {hasWarningBanner && (
        <Alert
          type="warning"
          showIcon
          banner
          message={
            <Space>
              <Text>{warningCount} 个系统告警</Text>
              <Button
                size="small"
                type="link"
                onClick={() => setExpanded((v) => !v)}
              >
                {expanded ? '收起' : '展开'} {expanded ? <UpOutlined /> : <DownOutlined />}
              </Button>
            </Space>
          }
        />
      )}

      <Collapse activeKey={expanded ? ['details'] : []} ghost>
        <Collapse.Panel key="details" header={null} forceRender>
          <Space direction="vertical" style={{ width: '100%' }}>
            {alerts.map((alert) => (
              <Alert
                key={alert.id}
                type={severityColor[alert.severity]}
                showIcon
                message={
                  <Space wrap>
                    <Tag color={severityColor[alert.severity]}>
                      {severityLabel[alert.severity]}
                    </Tag>
                    <Tag>{categoryLabel[alert.category]}</Tag>
                    <Text strong>{alert.message}</Text>
                  </Space>
                }
                description={
                  <Space direction="vertical" size="small" style={{ width: '100%' }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {dayjs(alert.created_at).format('YYYY-MM-DD HH:mm:ss')}
                    </Text>
                    {alert.detail_json && (
                      <Paragraph
                        type="secondary"
                        style={{ fontSize: 12, margin: 0 }}
                        ellipsis={{ rows: 2, expandable: true }}
                      >
                        <pre style={{ margin: 0 }}>
                          {JSON.stringify(alert.detail_json, null, 2)}
                        </pre>
                      </Paragraph>
                    )}
                    <Popconfirm
                      title="确认标记为已解决?"
                      onConfirm={() => handleResolve(alert.id)}
                      okText="确认"
                      cancelText="取消"
                    >
                      <Button
                        size="small"
                        type="primary"
                        ghost
                        icon={<CheckCircleOutlined />}
                      >
                        标记已解决
                      </Button>
                    </Popconfirm>
                  </Space>
                }
              />
            ))}
          </Space>
        </Collapse.Panel>
      </Collapse>
    </div>
  );
}

export default SystemAlertBanner;
