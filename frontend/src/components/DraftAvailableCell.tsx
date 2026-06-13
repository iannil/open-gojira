/**
 * DraftAvailableCell — show T+1 available / frozen / total shares for a SELL draft.
 *
 * Used in CockpitPage DraftList so the human sees, before going to their
 * broker, whether T+1 has frozen today's buys. Buy-listed symbols would
 * render "—" via the caller.
 */
import { useEffect, useState } from 'react';
import { Typography } from 'antd';

import { getAvailableQuantity } from '../api/client';
import type { AvailableQuantity } from '../api/types';

const { Text } = Typography;

export default function DraftAvailableCell({ code }: { code: string }) {
  const [info, setInfo] = useState<AvailableQuantity | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setInfo(null);
    setFailed(false);
    getAvailableQuantity(code)
      .then((data) => {
        if (!cancelled) setInfo(data);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [code]);

  if (failed) return <Text type="secondary">—</Text>;
  if (!info) return <Text type="secondary">加载中…</Text>;
  return (
    <div>
      <Text>可用 {info.available} 股</Text>
      {info.frozen > 0 && (
        <Text type="secondary"> (今日买入冻结 {info.frozen})</Text>
      )}
      <Text type="secondary"> / 共 {info.total}</Text>
    </div>
  );
}
