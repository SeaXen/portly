import React from 'react';
import { StatsData } from '../types';

interface StatsStripProps {
  stats: StatsData | null;
  onOpenSystemDrawer: (section?: string) => void;
}

export const StatsStrip: React.FC<StatsStripProps> = ({ stats, onOpenSystemDrawer }) => {
  if (!stats) return null;

  const segments = [
    { key: 'cpu', data: stats.cpu, isFirst: true },
    { key: 'memory', data: stats.memory, isFirst: false },
    { key: 'disk', data: stats.disk, isFirst: false },
    { key: 'network', data: stats.network, isFirst: false },
    { key: 'containers', data: stats.containers, isFirst: false },
    { key: 'listening', data: stats.listening, isFirst: false },
  ];

  return (
    <div
      className="c081"
      style={{
        width: '100%',
        cursor: 'pointer',
        userSelect: 'none',
      }}
      title="Click to view detailed system telemetry"
    >
      {segments.map(({ key, data, isFirst }) => {
        const cls = isFirst ? 'c082' : 'c088';
        const polyPoints = data?.sparkline || '0.0,20.0 60.0,20.0';

        return (
          <button
            type="button"
            key={key}
            className={cls}
            onClick={() => onOpenSystemDrawer(key)}
            aria-label={`${data?.label || key.toUpperCase()}${data?.value || '—'}${data?.context || ''} telemetry`}
            style={{
              transition: 'background-color 0.15s ease',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.02)')}
            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
          >
            <div className="c083">
              <div className="c084">{data?.label || key.toUpperCase()}</div>
              <div className="c085">{data?.value || '—'}</div>
              <div className="c086">{data?.context || ''}</div>
            </div>

            <svg
              width="50"
              height="22"
              viewBox="0 0 60 22"
              preserveAspectRatio="none"
              aria-hidden="true"
              className="c087"
            >
              <polyline
                points={polyPoints}
                fill="none"
                stroke="var(--accent)"
                strokeWidth="1.6"
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            </svg>
          </button>
        );
      })}
    </div>
  );
};
