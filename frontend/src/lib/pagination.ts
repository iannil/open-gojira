/**
 * Shared pagination config for list-style tables across the app.
 *
 * Max page size is 500 to bound the request + render cost; financial
 * tables with 5000+ rows (full A-share universe, multi-year trades)
 * should use server-side pagination instead of client-side at that scale.
 */
export const PAGE_SIZE_OPTIONS = [10, 20, 50, 100, 200, 500] as const;

export const DEFAULT_PAGE_SIZE = 50;

/** Spread into a Table's pagination prop. */
export const defaultPagination = {
  showSizeChanger: true,
  showQuickJumper: true,
  pageSizeOptions: PAGE_SIZE_OPTIONS as unknown as string[],
  showTotal: (total: number) => `共 ${total} 条`,
};
