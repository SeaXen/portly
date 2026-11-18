import React from 'react';

// Authored SVG icons — used instead of raw emoji/Unicode glyphs per DESIGN.md.
export type IconName = 'check' | 'x' | 'warning' | 'info' | 'bolt' | 'lock' | 'clock' | 'refresh';

interface IconProps {
  name: IconName;
  size?: number;
  color?: string;
  className?: string;
}

export const Icon: React.FC<IconProps> = ({ name, size = 16, color, className }) => {
  const paths: Record<IconName, React.ReactNode> = {
    check: <polyline points="20 6 9 17 4 12" />,
    x: <><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></>,
    warning: <><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></>,
    info: <><circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" /></>,
    bolt: <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />,
    lock: <><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></>,
    clock: <><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></>,
    refresh: <><polyline points="23 4 23 10 17 10" /><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" /></>,
  };

  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color || 'currentColor'}
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      style={{ flex: 'none', verticalAlign: 'middle' }}
    >
      {paths[name]}
    </svg>
  );
};
