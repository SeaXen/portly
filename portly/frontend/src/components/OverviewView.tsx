import React from 'react';
import { AppItem, Category, ConflictItem, StatsData } from '../types';

interface OverviewViewProps {
  apps: AppItem[];
  categories: Category[];
  conflicts: ConflictItem[];
  stats: StatsData | null;
  events: any[];
  onOpenDetail: (app: AppItem) => void;
  onSelectNav: (nav: string) => void;
}

export const OverviewView: React.FC<OverviewViewProps> = ({
  apps,
  categories,
  conflicts,
  events,
  onOpenDetail,
  onSelectNav,
}) => {
  const hostCount = apps.filter((a) => a.source === 'host').length;
  const dockerCount = apps.filter((a) => a.source === 'docker').length;
  const customCount = apps.filter((a) => a.source === 'custom').length;
  const activeCount = apps.filter((a) => a.status === 'up').length;
  const pinnedApps = apps.filter((a) => a.pinned);
  const topConsumers = [...apps]
    .filter((a) => (a.ram_mb || 0) > 0)
    .sort((a, b) => (b.ram_mb || 0) - (a.ram_mb || 0))
    .slice(0, 5);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', width: '100%' }}>
      {/* Metrics Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
        <div style={{ background: 'var(--surface-1)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '14px', padding: '18px' }}>
          <div style={{ fontSize: '12px', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Total Discovered</div>
          <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--text)', fontFamily: 'JetBrains Mono, monospace', margin: '6px 0' }}>
            {apps.length}
          </div>
          <div style={{ fontSize: '12px', color: 'var(--success)' }}>
            {activeCount} active services listening
          </div>
        </div>

        <div style={{ background: 'var(--surface-1)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '14px', padding: '18px' }}>
          <div style={{ fontSize: '12px', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Host Processes</div>
          <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--accent)', fontFamily: 'JetBrains Mono, monospace', margin: '6px 0' }}>
            {hostCount}
          </div>
          <div style={{ fontSize: '12px', color: 'var(--muted)' }}>
            Local machine listeners
          </div>
        </div>

        <div style={{ background: 'var(--surface-1)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '14px', padding: '18px' }}>
          <div style={{ fontSize: '12px', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Docker Containers</div>
          <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--success)', fontFamily: 'JetBrains Mono, monospace', margin: '6px 0' }}>
            {dockerCount}
          </div>
          <div style={{ fontSize: '12px', color: 'var(--muted)' }}>
            {customCount} custom Portly apps
          </div>
        </div>

        <div style={{ background: 'var(--surface-1)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '14px', padding: '18px' }}>
          <div style={{ fontSize: '12px', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Conflicts Detected</div>
          <div style={{ fontSize: '28px', fontWeight: 700, color: conflicts.length > 0 ? 'var(--danger)' : 'var(--success)', fontFamily: 'JetBrains Mono, monospace', margin: '6px 0' }}>
            {conflicts.length}
          </div>
          <div style={{ fontSize: '12px', color: conflicts.length > 0 ? 'var(--danger)' : 'var(--muted)' }}>
            {conflicts.length > 0 ? 'Requires attention' : 'All ports conflict-free'}
          </div>
        </div>
      </div>

      {/* Categories Breakdown */}
      <div style={{ background: 'var(--surface-1)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '14px', padding: '20px' }}>
        <h3 style={{ margin: '0 0 16px 0', fontSize: '16px', fontWeight: 600, color: 'var(--text)' }}>Category Distribution</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }}>
          {categories.map((c) => {
            const count = apps.filter((a) => a.category_id === c.id).length;
            const pct = apps.length > 0 ? Math.round((count / apps.length) * 100) : 0;
            return (
              <div key={c.id} style={{ background: 'var(--surface-2)', padding: '12px', borderRadius: '10px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: c.color }} />
                    <span style={{ fontWeight: 600, color: 'var(--text)', fontSize: '13px' }}>{c.name}</span>
                  </div>
                  <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '12px', color: 'var(--muted)' }}>{count}</span>
                </div>
                <div style={{ height: '4px', background: 'rgba(255,255,255,0.08)', borderRadius: '2px', overflow: 'hidden' }}>
                  <div style={{ width: `${pct}%`, height: '100%', backgroundColor: c.color }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Activity & Consumers */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px' }}>
        <div style={{ background: 'var(--surface-1)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '14px', padding: '20px' }}>
          <h3 style={{ margin: '0 0 14px 0', fontSize: '16px', fontWeight: 600, color: 'var(--text)' }}>Top Memory Consumers</h3>
          {topConsumers.length === 0 ? (
            <div style={{ fontSize: '13px', color: 'var(--muted)' }}>No memory data available.</div>
          ) : (
            topConsumers.map((app) => {
              const max = topConsumers[0].ram_mb || 1;
              const statsStale = app.stats_age_sec == null || app.stats_age_sec > 15;
              return (
                <div key={app.id} style={{ marginBottom: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginBottom: '4px' }}>
                    <button type="button" style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'var(--text)', fontSize: '13px', textAlign: 'left', minHeight: '24px', display: 'inline-flex', alignItems: 'center' }} onClick={() => onOpenDetail(app)}>
                      {app.name}
                    </button>
                    <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '12px', color: statsStale ? 'var(--muted)' : 'var(--accent)' }} title={statsStale ? 'Stale or unavailable stats' : undefined}>{app.ram_mb == null ? '—' : `${app.ram_mb} MB`}</span>
                  </div>
                  <div style={{ height: '4px', background: 'rgba(255,255,255,0.08)', borderRadius: '2px', overflow: 'hidden' }}>
                    <div style={{ width: `${Math.round(((app.ram_mb || 0) / max) * 100)}%`, height: '100%', background: 'var(--accent)' }} />
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div style={{ background: 'var(--surface-1)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '14px', padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--text)' }}>Recent Activity</h3>
            <button type="button" className="c078" style={{ height: '28px', fontSize: '12px' }} onClick={() => onSelectNav('history')}>
              View History →
            </button>
          </div>
          {events.length === 0 ? (
            <div style={{ fontSize: '13px', color: 'var(--muted)' }}>No activity recorded yet.</div>
          ) : (
            events.map((event) => (
              <div key={event.id} style={{ display: 'flex', gap: '10px', alignItems: 'flex-start', marginBottom: '10px', fontSize: '13px' }}>
                <span style={{ color: 'var(--muted)', fontFamily: 'JetBrains Mono, monospace', fontSize: '11px', whiteSpace: 'nowrap' }}>
                  {new Date(event.ts * 1000).toLocaleTimeString()}
                </span>
                <span style={{ color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={event.message}>
                  {event.message}
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Favorites / Pinned Services */}
      {pinnedApps.length > 0 && (
        <div style={{ background: 'var(--surface-1)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '14px', padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--text)' }}>Pinned Services ★</h3>
            <button type="button" className="c078" style={{ height: '28px', fontSize: '12px' }} onClick={() => onSelectNav('ports')}>
              View All Ports →
            </button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '14px' }}>
            {pinnedApps.map((app) => (
              <div
                key={app.id}
                role="button"
                tabIndex={0}
                aria-label={`View details for ${app.name}`}
                style={{
                  background: 'var(--surface-2)',
                  border: '1px solid rgba(255,255,255,0.08)',
                  borderRadius: '10px',
                  padding: '14px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
                onClick={() => onOpenDetail(app)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onOpenDetail(app);
                  }
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, color: 'var(--text)' }}>{app.name}</div>
                  <div style={{ fontFamily: 'JetBrains Mono, monospace', color: 'var(--accent)', fontSize: '13px', marginTop: '2px' }}>
                    {app.port || '—'}
                  </div>
                </div>
                <span
                  style={{
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    backgroundColor: app.status === 'unknown' ? 'var(--muted)' : (app.status === 'up' ? 'var(--success)' : 'var(--danger)'),
                  }}
                />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
