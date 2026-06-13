import { resolveSystemAlert } from '../../api/client';
import { useToastMutation } from '../../lib/useToastMutation';
import { alertKeys } from './queries';

/**
 * Resolve a single alert. Invalidates all system-alert query subtrees
 * (banner summary + detail list) so both refresh.
 */
export function useResolveAlertMutation() {
  return useToastMutation((id: number) => resolveSystemAlert(id), {
    successMsg: '已标记为已解决',
    invalidate: () => [alertKeys.all()],
  });
}

/**
 * Bulk-resolve via parallel POST. No backend bulk endpoint exists, so we
 * fan out client-side. Reports a single toast with success count.
 */
export function useBulkResolveAlertsMutation() {
  return useToastMutation(
    async (ids: number[]) => {
      const results = await Promise.allSettled(
        ids.map((id) => resolveSystemAlert(id)),
      );
      const ok = results.filter((r) => r.status === 'fulfilled').length;
      const failed = results.length - ok;
      return { ok, failed, total: ids.length };
    },
    {
      successMsg: (r) =>
        r.failed === 0
          ? `已解决 ${r.ok} 条告警`
          : `已解决 ${r.ok} / ${r.total}（${r.failed} 条失败）`,
      invalidate: () => [alertKeys.all()],
    },
  );
}
