import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

/* ── Types ────────────────────────────────────────────────────────── */

export interface TabItem {
  /** Unique key (pathname for static pages, pathname+hash for dynamic) */
  key: string;
  /** Full pathname, e.g. "/portfolio" or "/stock/600519" */
  pathname: string;
  /** Display title shown on the tab */
  title: string;
  /** Whether this tab can be closed (home tab is always pinned) */
  closable: boolean;
}

interface TabContextValue {
  tabs: TabItem[];
  activeKey: string;
  openTab: (pathname: string, title: string) => void;
  closeTab: (key: string) => void;
  activateTab: (key: string) => void;
  activeTab: TabItem | undefined;
}

/* ── Context ──────────────────────────────────────────────────────── */

const TabContext = createContext<TabContextValue | null>(null);

/* ── Provider ─────────────────────────────────────────────────────── */

export function TabProvider({ children }: { children: ReactNode }) {
  const [tabs, setTabs] = useState<TabItem[]>([
    { key: '/', pathname: '/', title: '主看板', closable: false },
  ]);
  const [activeKey, setActiveKey] = useState('/');
  const idCounter = useRef(0);

  const openTab = useCallback((pathname: string, title: string) => {
    const key = pathname === '/' ? '/' : `${pathname}__${++idCounter.current}`;

    setTabs((prev) => {
      // Check if a tab for this exact pathname already exists
      const existing = prev.find((t) => t.pathname === pathname);
      if (existing) {
        // Reactivate existing tab
        setActiveKey(existing.key);
        return prev;
      }
      // Add new tab and activate it
      const newTab: TabItem = {
        key,
        pathname,
        title,
        closable: pathname !== '/',
      };
      setActiveKey(key);
      return [...prev, newTab];
    });
  }, []);

  const closeTab = useCallback((key: string) => {
    setTabs((prev) => {
      const tab = prev.find((t) => t.key === key);
      // Never close non-closable tabs (e.g. the pinned home tab)
      if (!tab || !tab.closable) return prev;
      const tabIdx = prev.indexOf(tab);
      const remaining = prev.filter((t) => t.key !== key);

      // If closing the active tab, activate a neighbor
      setActiveKey((currentActive) => {
        if (currentActive !== key) return currentActive;
        const nextIdx = remaining.length > 0
          ? Math.min(tabIdx, remaining.length - 1)
          : -1;
        return nextIdx >= 0 ? remaining[nextIdx].key : '/';
      });

      return remaining.length === 0
        ? [{ key: '/', pathname: '/', title: '主看板', closable: false }]
        : remaining;
    });
  }, []);

  const activateTab = useCallback((key: string) => {
    setActiveKey(key);
  }, []);

  const activeTab = useMemo(
    () => tabs.find((t) => t.key === activeKey),
    [tabs, activeKey],
  );

  const value = useMemo<TabContextValue>(
    () => ({ tabs, activeKey, openTab, closeTab, activateTab, activeTab }),
    [tabs, activeKey, openTab, closeTab, activateTab, activeTab],
  );

  return <TabContext.Provider value={value}>{children}</TabContext.Provider>;
}

/* ── Hook ─────────────────────────────────────────────────────────── */

export function useTabs(): TabContextValue {
  const ctx = useContext(TabContext);
  if (!ctx) throw new Error('useTabs must be used within a <TabProvider>');
  return ctx;
}
