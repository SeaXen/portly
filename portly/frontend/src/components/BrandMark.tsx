import React from 'react';

interface BrandMarkProps {
  size?: number;
  withFrame?: boolean;
  className?: string;
}

/** Signature Portly architectural "P" port-gateway & live beacon emblem. */
export const BrandMark: React.FC<BrandMarkProps> = ({ size = 28, withFrame = false, className }) => {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 128 128"
      fill="none"
      aria-hidden="true"
      focusable="false"
      style={{ flex: 'none', display: 'block' }}
    >
      {withFrame && (
        <rect
          x="4"
          y="4"
          width="120"
          height="120"
          rx="28"
          fill="#0E1322"
          stroke="currentColor"
          strokeOpacity="0.16"
          strokeWidth="2"
        />
      )}
      <path
        fillRule="evenodd"
        fill="currentColor"
        fillOpacity="0.88"
        d="M 43.5 28 L 69 28 A 23 23 0 0 1 92 51 A 23 23 0 0 1 69 74 L 43.5 74 Z M 54 40 L 67 40 A 11 11 0 0 1 78 51 A 11 11 0 0 1 67 62 L 54 62 Z"
      />
      <circle cx="67" cy="51" r="6.2" fill="var(--success, #5EEAD4)" />
      <rect x="36" y="28" width="15" height="72" rx="7.5" fill="currentColor" />
    </svg>
  );
};
