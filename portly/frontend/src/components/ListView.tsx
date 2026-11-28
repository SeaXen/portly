import React from 'react';
import { AppItem, Category } from '../types';
import { EmptyState } from './EmptyState';

interface ListViewProps {
  apps: AppItem[];
  onOpenDetail: (app: AppItem) => void;
  categories: Category[];
}

export const ListView: React.FC<ListViewProps> = React.memo(({ apps, onOpenDetail }) => {
  if (apps.length === 0) return <EmptyState />;

  return (
    <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '4px' }}>
      {apps.map((app) => (
        <div
          key={app.id}
          className="c053 portly-list-row"
          tabIndex={0}
          style={{
            height: '40px',
            background: 'var(--surface-2)',
            border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: '8px',
            padding: '0 14px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
            minWidth: 0,
            overflow: 'hidden',
            cursor: 'pointer',
          }}
          onClick={() => onOpenDetail(app)}
          onKeyDown={(e) => {
            if (e.target !== e.currentTarget) return;
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              onOpenDetail(app);
            }
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flex: '1 1 0', minWidth: 0, overflow: 'hidden' }}>
            <span
              style={{
                width: '7px',
                height: '7px',
                borderRadius: '50%',
                flexShrink: 0,
                backgroundColor: app.status === 'unknown' ? 'var(--muted)' : (app.status === 'up' ? 'var(--success)' : 'var(--danger)'),
              }}
            />
            <button type="button" className="app-name-btn" style={{ fontWeight: 600, color: 'var(--text)', fontSize: '14px', flex: '0 1 auto', minWidth: 0 }}>{app.name}</button>
            <span style={{ fontFamily: 'JetBrains Mono, monospace', color: 'var(--accent)', fontWeight: 600, flexShrink: 0 }}>
              {app.port || '—'}
            </span>
            <span className="portly-list-sub" style={{ fontSize: '12px', color: 'var(--muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>
              {app.source === 'docker' ? app.image : app.process_name}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexShrink: 0 }}>
            <span className="portly-list-secondary" style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '12px', color: 'var(--muted)' }}>
              {app.bind}
            </span>
            <span className="portly-list-secondary" style={{ fontSize: '12px', color: app.stats_age_sec == null || app.stats_age_sec > 15 ? 'var(--muted)' : 'var(--text)' }} title={app.stats_age_sec == null || app.stats_age_sec > 15 ? 'Stale or unavailable stats' : undefined}>
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
});
