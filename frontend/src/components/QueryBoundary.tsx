import type { ReactNode } from 'react';
import { Alert, Button, Empty, Spin } from 'antd';

export interface QueryLike<T> {
  isLoading: boolean;
  isFetching?: boolean;
  isError: boolean;
  error: unknown;
  data: T | undefined;
  refetch?: () => unknown;
}

export interface QueryBoundaryProps<T> {
  query: QueryLike<T>;
  isEmpty?: (data: T) => boolean;
  emptyRender?: ReactNode;
  errorRender?: (err: Error, retry: () => void) => ReactNode;
  skeleton?: ReactNode;
  children: (data: T, isFetching: boolean) => ReactNode;
}

export default function QueryBoundary<T>(props: QueryBoundaryProps<T>) {
  const { query } = props;

  if (query.isLoading) {
    return <>{props.skeleton ?? <Spin />}</>;
  }

  if (query.isError) {
    const err = query.error as Error;
    const retry = () => void query.refetch?.();
    return (
      <>
        {props.errorRender ? (
          props.errorRender(err, retry)
        ) : (
          <Alert
            type="error"
            showIcon
            message={err.message}
            action={<Button size="small" onClick={retry}>重试</Button>}
          />
        )}
      </>
    );
  }

  const data = query.data as T;
  if (props.isEmpty && props.isEmpty(data)) {
    return <>{props.emptyRender ?? <Empty />}</>;
  }

  return <>{props.children(data, !!query.isFetching)}</>;
}
