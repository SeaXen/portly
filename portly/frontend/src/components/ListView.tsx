import React from 'react';
import { AppItem, Category } from '../types';

interface ListViewProps {
  apps: AppItem[];
  onOpenDetail: (app: AppItem) => void;
  categories: Category[];
}

export const ListView: React.FC<ListViewProps> = ({ apps, onOpenDetail }) => {
  return (
    <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '4px' }}>
      {apps.map((app) => (
        <div
          key={app.id}
          className="c053"
          style={{
            height: '40px',
            background: 'var(--surface-2)',
            border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: '8px',
            padding: '0 14px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            cursor: 'pointer',
          }}
          onClick={() => onOpenDetail(app)}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span
              style={{
                width: '7px',
                height: '7px',
                borderRadius: '50%',
                backgroundColor: app.status === 'unknown' ? 'var(--muted)' : (app.status === 'up' ? 'var(--success)' : 'var(--danger)'),
              }}
            />
            <button type="button" className="app-name-btn" style={{ fontWeight: 600, color: 'var(--text)', fontSize: '14px' }}>{app.name}</button>
            <span style={{ fontFamily: 'JetBrains Mono, monospace', color: 'var(--accent)', fontWeight: 600 }}>
              {app.port || '—'}
            </span>
            <span style={{ fontSize: '12px', color: 'var(--muted)' }}>
              {app.source === 'docker' ? app.image : app.process_name}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '12px', color: 'var(--muted)' }}>
              {app.bind}
            </span>
            <span style={{ fontSize: '12px', color: app.stats_age_sec == null || app.stats_age_sec > 15 ? 'var(--muted)' : 'var(--muted)' }} title={app.stats_age_sec == null || app.stats_age_sec > 15 ? 'Stale or unavailable stats' : undefined}>
              CPU {app.cpu_percent == null ? '—' : `${app.cpu_percent}%`} · {app.ram_mb == null ? '—' : `${app.ram_mb} MB`}{app.stats_age_sec == null || app.stats_age_sec > 15 ? ' (stale)' : ''}
            </span>
            <span className="c109" style={{ textTransform: 'capitalize' }}>
              {app.source}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
};
