// Inline SVG icons
type P = { className?: string };
const base = "w-4 h-4 stroke-current";

export const IDashboard = ({ className }: P) => (
  <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.6" className={className ?? base}>
    <rect x="3" y="3" width="7" height="7" rx="1.5" />
    <rect x="14" y="3" width="7" height="7" rx="1.5" />
    <rect x="3" y="14" width="7" height="7" rx="1.5" />
    <rect x="14" y="14" width="7" height="7" rx="1.5" />
  </svg>
);

export const IUser = ({ className }: P) => (
  <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.6" className={className ?? base}>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21a8 8 0 0116 0" strokeLinecap="round" />
  </svg>
);

export const IWrench = ({ className }: P) => (
  <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.6" className={className ?? base}>
    <path d="M14.7 6.3a4 4 0 105.4 5.4l-3.3-3.3 1.4-1.4 3.3 3.3a6 6 0 11-8.5 8.5L5 12.5l-2 2L1 12.5l8-8 2 2-2 2 6 6z" strokeLinejoin="round" />
  </svg>
);

export const IChip = ({ className }: P) => (
  <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.6" className={className ?? base}>
    <rect x="6" y="6" width="12" height="12" rx="2" />
    <rect x="9" y="9" width="6" height="6" rx="1" />
    <path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3" strokeLinecap="round" />
  </svg>
);

export const ITimeline = ({ className }: P) => (
  <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.6" className={className ?? base}>
    <circle cx="6" cy="6" r="2" />
    <circle cx="6" cy="12" r="2" />
    <circle cx="6" cy="18" r="2" />
    <path d="M10 6h11M10 12h11M10 18h11" strokeLinecap="round" />
  </svg>
);

export const ISearch = ({ className }: P) => (
  <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.6" className={className ?? base}>
    <circle cx="11" cy="11" r="7" />
    <path d="M21 21l-4.3-4.3" strokeLinecap="round" />
  </svg>
);

export const IZap = ({ className }: P) => (
  <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.6" className={className ?? base}>
    <path d="M13 2L4 14h7l-1 8 9-12h-7l1-8z" strokeLinejoin="round" />
  </svg>
);

export const ICog = ({ className }: P) => (
  <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.6" className={className ?? base}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z" />
  </svg>
);

export const IMoon = ({ className }: P) => (
  <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.6" className={className ?? base}>
    <path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z" strokeLinejoin="round" />
  </svg>
);

export const ISun = ({ className }: P) => (
  <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.6" className={className ?? base}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.5 1.5M17.6 17.6l1.5 1.5M4.9 19.1l1.5-1.5M17.6 6.4l1.5-1.5" strokeLinecap="round" />
  </svg>
);

export const IRefresh = ({ className }: P) => (
  <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.6" className={className ?? base}>
    <path d="M3 12a9 9 0 0115-6.7L21 8M21 3v5h-5M21 12a9 9 0 01-15 6.7L3 16M3 21v-5h5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const IChat = ({ className }: P) => (
  <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.6" className={className ?? base}>
    <path d="M21 12a8 8 0 11-3-6.2L21 4l-1.2 3A8 8 0 0121 12z" strokeLinecap="round" strokeLinejoin="round" />
    <circle cx="9" cy="12" r="1" fill="currentColor" />
    <circle cx="13" cy="12" r="1" fill="currentColor" />
    <circle cx="17" cy="12" r="1" fill="currentColor" />
  </svg>
);

export const IChevronRight = ({ className }: P) => (
  <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.8" className={className ?? base}>
    <path d="M9 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
