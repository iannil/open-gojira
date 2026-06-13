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
