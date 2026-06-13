import {
  createNotificationChannel,
  createRiskRule,
  deleteNotificationChannel,
  deleteRiskRule,
  testNotificationChannel,
  updateNotificationChannel,
  updateRiskRule,
} from '../../api/client';
import type {
  NotificationChannelCreate,
  NotificationChannelUpdate,
  RiskRuleCreate,
  RiskRuleUpdate,
} from '../../api/types';
import { useToastMutation } from '../../lib/useToastMutation';
import { monitoringKeys } from './queries';

const INVALIDATE_ALL = () => [monitoringKeys.all()];

// ── Channels ───────────────────────────────────────────────────────────

export function useCreateChannelMutation() {
  return useToastMutation(
    (payload: NotificationChannelCreate) => createNotificationChannel(payload),
    { successMsg: '已新增', invalidate: INVALIDATE_ALL },
  );
}

export function useUpdateChannelMutation() {
  return useToastMutation(
    (args: { id: number; payload: NotificationChannelUpdate }) =>
      updateNotificationChannel(args.id, args.payload),
    {
      successMsg: (r) => (r.enabled === false ? '已停用' : '已更新'),
      invalidate: INVALIDATE_ALL,
    },
  );
}

export function useDeleteChannelMutation() {
  return useToastMutation((id: number) => deleteNotificationChannel(id), {
    successMsg: '已删除',
    invalidate: INVALIDATE_ALL,
  });
}

/** Test notification — success/failure reported inline by backend, not as
 * a typical mutation success. */
export function useTestChannelMutation() {
  return useToastMutation((id: number) => testNotificationChannel(id), {
    successMsg: (r) => (r.success ? '测试通知已发送' : `发送失败：${r.error ?? '未知错误'}`),
    errorMsg: '测试请求失败',
  });
}

// ── Risk Rules ─────────────────────────────────────────────────────────

export function useCreateRiskRuleMutation() {
  return useToastMutation(
    (payload: RiskRuleCreate & { peak_price?: number | null }) => createRiskRule(payload),
    { successMsg: '已新增', invalidate: INVALIDATE_ALL },
  );
}

export function useUpdateRiskRuleMutation() {
  return useToastMutation(
    (args: { id: number; payload: RiskRuleUpdate }) => updateRiskRule(args.id, args.payload),
    {
      successMsg: (r) => (r.enabled === false ? '已停用' : '已更新'),
      invalidate: INVALIDATE_ALL,
    },
  );
}

export function useDeleteRiskRuleMutation() {
  return useToastMutation((id: number) => deleteRiskRule(id), {
    successMsg: '已删除',
    invalidate: INVALIDATE_ALL,
  });
}
