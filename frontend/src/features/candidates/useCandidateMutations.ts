import { removeCandidate, updateCandidate } from '../../api/client';
import { useToastMutation } from '../../lib/useToastMutation';
import { candidateKeys } from './queries';

export function useTogglePinCandidateMutation() {
  return useToastMutation(
    (args: { id: number; pinned: boolean }) =>
      updateCandidate(args.id, { pinned: args.pinned }),
    {
      successMsg: (r) => (r.pinned ? '已固定' : '已取消固定'),
      invalidate: () => [candidateKeys.all()],
    },
  );
}

export function useRemoveCandidateMutation() {
  return useToastMutation((id: number) => removeCandidate(id), {
    successMsg: '已移出',
    invalidate: () => [candidateKeys.all()],
  });
}

/**
 * Batch variants for the merged-by-stock candidate view. A single stock can be
 * backed by multiple candidate rows (one per plan that flagged it); these
 * apply the user's intent across every active candidate row for that stock.
 */
export function useTogglePinCandidatesMutation() {
  return useToastMutation(
    (args: { ids: number[]; pinned: boolean }) =>
      Promise.all(
        args.ids.map((id) => updateCandidate(id, { pinned: args.pinned })),
      ),
    {
      successMsg: (data) => (data[0]?.pinned ? '已固定' : '已取消固定'),
      invalidate: () => [candidateKeys.all()],
    },
  );
}

export function useRemoveCandidatesMutation() {
  return useToastMutation(
    (ids: number[]) => Promise.all(ids.map((id) => removeCandidate(id))),
    {
      successMsg: '已移出',
      invalidate: () => [candidateKeys.all()],
    },
  );
}
