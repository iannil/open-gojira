import {
  useMutation,
  useQueryClient,
  type QueryKey,
  type UseMutationOptions,
} from '@tanstack/react-query';
import { useAntdStatic } from '../hooks/useAntdStatic';

export interface ToastMutationOptions<TData, TVars, TContext = unknown>
  extends UseMutationOptions<TData, Error, TVars, TContext> {
  successMsg?: string | ((data: TData) => string);
  errorMsg?: string | false | ((err: Error) => string);
  invalidate?: QueryKey[] | ((data: TData) => QueryKey[]);
}

export function useToastMutation<TData, TVars, TContext = unknown>(
  mutationFn: (vars: TVars) => Promise<TData>,
  options: ToastMutationOptions<TData, TVars, TContext> = {},
) {
  const { message } = useAntdStatic();
  const queryClient = useQueryClient();

  return useMutation<TData, Error, TVars, TContext>({
    mutationFn,
    retry: 0,
    ...options,
    onSuccess: async (data, vars, onMutateResult, context) => {
      if (options.successMsg) {
        message.success(
          typeof options.successMsg === 'function'
            ? options.successMsg(data)
            : options.successMsg,
        );
      }
      const keys =
        typeof options.invalidate === 'function'
          ? options.invalidate(data)
          : (options.invalidate ?? []);
      await Promise.all(
        keys.map((k) => queryClient.invalidateQueries({ queryKey: k })),
      );
      return options.onSuccess?.(data, vars, onMutateResult, context);
    },
    onError: (err, vars, onMutateResult, context) => {
      if (options.errorMsg !== false) {
        const msg =
          typeof options.errorMsg === 'function'
            ? options.errorMsg(err)
            : (options.errorMsg ?? `操作失败：${err.message}`);
        message.error(msg);
      }
      return options.onError?.(err, vars, onMutateResult, context);
    },
  });
}
