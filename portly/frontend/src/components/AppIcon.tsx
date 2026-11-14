import React, { useState } from 'react';

interface AppIconProps {
  appId: string;
  name: string;
  source: string;
  size?: number;
  className?: string;
}

export const AppIcon: React.FC<AppIconProps> = ({
  appId,
  name,
  source,
  size = 30,
  className,
}) => {
  const [loadFailed, setLoadFailed] = useState(false);
  const initial = name && name.trim() ? name.trim().charAt(0).toUpperCase() : '?';

  if (loadFailed) {
    return (
      <div
        className={className}
        style={{
          width: `${size}px`,
          height: `${size}px`,
          borderRadius: size >= 32 ? '9px' : '7px',
          background: source === 'docker' ? 'rgba(94, 234, 212, 0.15)' : 'rgba(140, 158, 255, 0.15)',
          color: source === 'docker' ? '#5EEAD4' : '#8C9EFF',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontWeight: 700,
          fontSize: `${Math.round(size * 0.44)}px`,
          flexShrink: 0,
          userSelect: 'none',
        }}
        aria-hidden="true"
      >
        {initial}
      </div>
    );
  }

  return (
    <div
      className={className}
      style={{
        width: `${size}px`,
        height: `${size}px`,
        borderRadius: size >= 32 ? '9px' : '7px',
        background: 'rgba(255, 255, 255, 0.04)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        overflow: 'hidden',
        userSelect: 'none',
      }}
      aria-hidden="true"
    >
      <img
        src={`/api/apps/${encodeURIComponent(appId)}/favicon`}
        alt=""
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'contain',
          borderRadius: size >= 32 ? '9px' : '7px',
        }}
        onError={() => setLoadFailed(true)}
      />
    </div>
  );
};
