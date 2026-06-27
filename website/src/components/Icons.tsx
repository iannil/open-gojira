/* ═══════════════════════════════════════════════════════════════════════════
   Open Gojira 官网 — 自定义 SVG 图标组件
   设计语言：monoline, 24×24 viewBox, stokeWidth=1.5, currentColor
   风格：几何/精密/力量感，与品牌调性一致
   ═══════════════════════════════════════════════════════════════════════════ */

interface IconProps {
  size?: number;
  className?: string;
}

function IconWrap({ size = 24, className, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export function IconFastAPI({ size }: IconProps) {
  return (
    <IconWrap size={size}>
      {/* Lightning bolt inside brackets */}
      <path d="M12 2L6 13h4l-1 9 7-12h-4l1-8z" />
      <rect x="2" y="3" width="2" height="18" rx="1" />
      <rect x="20" y="3" width="2" height="18" rx="1" />
    </IconWrap>
  );
}

export function IconReact({ size }: IconProps) {
  return (
    <IconWrap size={size}>
      {/* Atom orbit */}
      <ellipse cx="12" cy="12" rx="10" ry="3.5" transform="rotate(0 12 12)" opacity="0.7" />
      <ellipse cx="12" cy="12" rx="10" ry="3.5" transform="rotate(60 12 12)" opacity="0.7" />
      <ellipse cx="12" cy="12" rx="10" ry="3.5" transform="rotate(120 12 12)" opacity="0.7" />
      <circle cx="12" cy="12" r="2" />
    </IconWrap>
  );
}

export function IconPostgreSQL({ size }: IconProps) {
  return (
    <IconWrap size={size}>
      {/* Database cylinder */}
      <ellipse cx="12" cy="6" rx="7" ry="2.5" />
      <path d="M5 6v12c0 1.38 3.13 2.5 7 2.5s7-1.12 7-2.5V6" />
      <path d="M5 12c0 1.38 3.13 2.5 7 2.5s7-1.12 7-2.5" />
    </IconWrap>
  );
}

export function IconLixinger({ size }: IconProps) {
  return (
    <IconWrap size={size}>
      {/* Magnifying glass + chart line */}
      <circle cx="10" cy="10" r="6" />
      <path d="M14.5 14.5L20 20" />
      <path d="M6 11l2-3 2 2 2-4 2 3" strokeWidth="1.2" />
    </IconWrap>
  );
}

export function IconGLM({ size }: IconProps) {
  return (
    <IconWrap size={size}>
      {/* Diamond / neural abstraction */}
      <path d="M12 2L20 12L12 22L4 12Z" />
      <circle cx="12" cy="12" r="2" />
      <path d="M12 4v4M12 16v4M6 8l3 2M15 14l3 2M6 16l3-2M15 10l3-2" strokeWidth="1" opacity="0.5" />
    </IconWrap>
  );
}

export function IconECharts({ size }: IconProps) {
  return (
    <IconWrap size={size}>
      {/* Bar chart + line overlay */}
      <rect x="4" y="14" width="3" height="7" />
      <rect x="9" y="9" width="3" height="12" />
      <rect x="14" y="5" width="3" height="16" />
      <rect x="19" y="11" width="2" height="10" />
      <path d="M4 16l5-5 5-4 5 3" strokeWidth="1.2" />
    </IconWrap>
  );
}

export function IconAntDesign({ size }: IconProps) {
  return (
    <IconWrap size={size}>
      {/* Ant / structured hex grid */}
      <path d="M12 2L4 7v10l8 5 8-5V7Z" />
      <path d="M12 2v5M12 12v10M4 7l8 5 8-5" />
      <circle cx="12" cy="12" r="1.5" />
    </IconWrap>
  );
}

export function IconAPScheduler({ size }: IconProps) {
  return (
    <IconWrap size={size}>
      {/* Clock with timer ring */}
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 3" />
      <circle cx="12" cy="12" r="11" strokeWidth="0.8" strokeDasharray="3 2" />
    </IconWrap>
  );
}

/* ── Pipeline geometric icons ─────────────────────────────────────────── */

export function IconPool({ size }: IconProps) {
  return (
    <IconWrap size={size}>
      <circle cx="12" cy="12" r="8" />
      <circle cx="10" cy="10" r="1.5" />
      <circle cx="14" cy="10" r="1.5" />
      <circle cx="12" cy="14" r="1.5" />
    </IconWrap>
  );
}

export function IconResearch({ size }: IconProps) {
  return (
    <IconWrap size={size}>
      <circle cx="10" cy="10" r="5" />
      <path d="M14 14l4 4" />
      <path d="M3 3h18v18H3z" />
      <circle cx="8" cy="8" r="1" />
      <circle cx="16" cy="8" r="1" />
      <path d="M8 14c1.5 1.5 4.5 1.5 6 0" />
    </IconWrap>
  );
}

export function IconDraft({ size }: IconProps) {
  return (
    <IconWrap size={size}>
      <path d="M5 3h10l4 4v14H5z" />
      <path d="M15 3v4h4" />
      <path d="M9 12h6M9 16h4" />
      <circle cx="12" cy="12" r="0" />
    </IconWrap>
  );
}

export function IconExecute({ size }: IconProps) {
  return (
    <IconWrap size={size}>
      <circle cx="12" cy="12" r="9" />
      <path d="M10 8l6 4-6 4z" />
    </IconWrap>
  );
}

export function IconTrack({ size }: IconProps) {
  return (
    <IconWrap size={size}>
      <path d="M4 20l4-6 4 3 8-9" />
      <path d="M16 8h5v5" />
    </IconWrap>
  );
}

/* ── Engine icons ─────────────────────────────────────────────────────── */

export function IconValue({ size }: IconProps) {
  return (
    <IconWrap size={size}>
      <path d="M12 2L2 7l10 5 10-5Z" />
      <path d="M2 17l10 5 10-5" />
      <path d="M2 12l10 5 10-5" />
    </IconWrap>
  );
}

export function IconChokepoint({ size }: IconProps) {
  return (
    <IconWrap size={size}>
      <path d="M12 2v20" />
      <path d="M2 12h20" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="12" cy="12" r="8" strokeDasharray="2 2" />
    </IconWrap>
  );
}
