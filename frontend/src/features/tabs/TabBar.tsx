import { useCallback, useRef, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { CloseOutlined } from '@ant-design/icons';
import { useTabs } from './TabContext';

/* ── TabBar ───────────────────────────────────────────────────────── */

export default function TabBar() {
  const { tabs, activeKey, closeTab, activateTab } = useTabs();
  const navigate = useNavigate();
  const location = useLocation();
  const scrollRef = useRef<HTMLDivElement>(null);
  const activeBtnRef = useRef<HTMLButtonElement>(null);

  /* ── Sync active tab URL when activated ────────────────────────── */
  const handleTabClick = useCallback(
    (key: string, pathname: string) => {
      activateTab(key);
      if (pathname !== location.pathname) {
        navigate(pathname);
      }
    },
    [activateTab, navigate, location.pathname],
  );

  /* ── Close tab and navigate ────────────────────────────────────── */
  const handleClose = useCallback(
    (e: React.MouseEvent, key: string) => {
      e.stopPropagation();
      const tab = tabs.find((t) => t.key === key);
      if (!tab) return;

      closeTab(key);

      // If closing the currently focused tab, navigate to remaining tab
      if (key === activeKey) {
        const remaining = tabs.filter((t) => t.key !== key);
        if (remaining.length > 0) {
          const next = remaining[Math.min(tabs.indexOf(tab), remaining.length - 1)];
          navigate(next.pathname);
        } else {
          navigate('/');
        }
      }
    },
    [tabs, activeKey, closeTab, navigate],
  );

  /* ── Scroll active tab into view ───────────────────────────────── */
  useEffect(() => {
    if (activeBtnRef.current && scrollRef.current) {
      const container = scrollRef.current;
      const btn = activeBtnRef.current;
      const containerRect = container.getBoundingClientRect();
      const btnRect = btn.getBoundingClientRect();

      if (
        btnRect.left < containerRect.left ||
        btnRect.right > containerRect.right
      ) {
        btn.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
      }
    }
  }, [activeKey]);

  /* ── Middle-click to close ─────────────────────────────────────── */
  const handleMouseDown = useCallback(
    (e: React.MouseEvent, key: string) => {
      if (e.button === 1) {
        // Middle mouse button
        const tab = tabs.find((t) => t.key === key);
        if (tab && tab.closable) {
          handleClose(e as unknown as React.MouseEvent, key);
        }
      }
    },
    [tabs, handleClose],
  );

  if (tabs.length === 0) return null;

  return (
    <div className="tab-bar" role="tablist" aria-label="打开的面板">
      <div className="tab-bar-scroll" ref={scrollRef}>
        {tabs.map((tab) => {
          const isActive = tab.key === activeKey;
          return (
            <button
              key={tab.key}
              ref={isActive ? activeBtnRef : undefined}
              type="button"
              className={`tab-bar-tab${isActive ? ' active' : ''}`}
              role="tab"
              aria-selected={isActive}
              onClick={() => handleTabClick(tab.key, tab.pathname)}
              onMouseDown={(e) => handleMouseDown(e, tab.key)}
              title={tab.title}
            >
              <span className="tab-bar-tab-title">{tab.title}</span>
              {tab.closable && (
                <span
                  className="tab-bar-tab-close"
                  onClick={(e) => handleClose(e, tab.key)}
                  role="button"
                  aria-label={`关闭 ${tab.title}`}
                  tabIndex={-1}
                >
                  <CloseOutlined />
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
