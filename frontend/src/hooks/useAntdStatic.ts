import { App } from 'antd';

/**
 * Hook to access antd static APIs (message, notification, modal) via context.
 * Requires <App> wrapper in the component tree.
 *
 * Usage: const { message, notification, modal } = useAntdStatic();
 */
export function useAntdStatic() {
  const { message, notification, modal } = App.useApp();
  return { message, notification, modal };
}
