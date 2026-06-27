import { updateThesisVariables } from '../../api/client';
import type { ThesisVariable } from '../../api/types';
import { useToastMutation } from '../../lib/useToastMutation';
import { stockKeys } from './queries';

export function useUpdateThesisVariablesMutation(code: string) {
  return useToastMutation(
    (vars: ThesisVariable[]) => updateThesisVariables(code, vars),
    {
      successMsg: '变量已更新',
      invalidate: () => [stockKeys.detail(code)],
    },
  );
}
