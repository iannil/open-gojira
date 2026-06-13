import { cancelDraft, executeDraft } from '../../api/client';
import type { ExecuteDraftPayload } from '../../api/client';
import { useToastMutation } from '../../lib/useToastMutation';
import { draftKeys } from './queries';

/**
 * Execute a draft via discipline-checklist + broker fill.
 * Invalidates drafts + trades + cockpit so Cockpit's "today's drafts"
 * section and the trades page both refresh.
 */
export function useExecuteDraftMutation() {
  return useToastMutation(
    (args: { id: number; payload: ExecuteDraftPayload }) =>
      executeDraft(args.id, args.payload),
    {
      successMsg: '已登记成交 + 记录 trade',
      invalidate: () => [draftKeys.all(), ['trades'], ['cockpit'], ['holdings']],
    },
  );
}

export function useCancelDraftMutation() {
  return useToastMutation((id: number) => cancelDraft(id), {
    successMsg: '已取消草稿',
    invalidate: () => [draftKeys.all(), ['cockpit']],
  });
}
