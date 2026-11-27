import React from 'react';
import { AppItem, Category } from '../types';
import { AppIcon } from './AppIcon';
import { Icon } from './Icon';
import { EmptyState } from './EmptyState';

interface TableViewProps {
  apps: AppItem[];
  selectedIds: string[];
  onToggleSelect: (id: string) => void;
  onSelectAll: () => void;
  categories: Category[];
  density: 'compact' | 'comfy';
  onOpenDetail: (app: AppItem) => void;
  onQuickStart: (app: AppItem, e: React.MouseEvent) => void;
  onQuickStop: (app: AppItem, e: React.MouseEvent) => void;
  onQuickLogs: (app: AppItem, e: React.MouseEvent) => void;
  onAdoptApp?: (app: AppItem) => void;
  safeMode: boolean;
  readOnly?: boolean;
  visibleFields?: Record<string, boolean>;
  groupBy?: string;
}

export const TableView: React.FC<TableViewProps> = ({
  apps,
  selectedIds,
  onToggleSelect,
  onSelectAll,
  categories,
  density,
  onOpenDetail,
  onQuickStart,
  onQuickStop,
  onQuickLogs,
  onAdoptApp,
  safeMode,
  readOnly = false,
  visibleFields = {},
  groupBy = 'none',
}) => {
  const allSelected = apps.length > 0 && apps.every((a) => selectedIds.includes(a.id));

  const getCategoryColor = (catId: string) => {
    const c = categories.find((x) => x.id === catId);
    return c?.color || 'var(--accent)';
  };

  const getCategoryName = (catId: string) => {
    const c = categories.find((x) => x.id === catId);
    return c?.name || catId;
  };

  const padStyle = density === 'compact' ? { padding: '0 16px', height: '48px' } : { padding: '0 18px', height: '58px' };

  // Honor CustomizeDrawer field toggles: hidden cells use display:none so they
  // drop out of grid flow, matching the tracks removed from the template.
  const showPort = visibleFields.port !== false;
  const showSource = visibleFields.source !== false;
  const showBind = visibleFields.bind !== false;
  const showCpuRam = visibleFields.cpuram !== false;
  const showUptime = visibleFields.uptime !== false;
  const hide = (show: boolean) => (show ? undefined : ('none' as const));
  const gridCols = [
    '32px', '24px', 'minmax(140px, 2.5fr)',
    showPort ? '85px' : null,
    showSource ? '75px' : null,
    '110px',
    showBind ? '105px' : null,
    '70px',
    showCpuRam ? '86px' : null,
    showCpuRam ? '70px' : null,
    showUptime ? '90px' : null,
    '140px',
  ].filter(Boolean).join(' ');

  // Grouping logic
  const groups: Array<{ name: string; items: AppItem[] }> = [];
  if (groupBy === 'category') {
    categories.forEach((c) => {
      const items = apps.filter((a) => a.category_id === c.id);
      if (items.length > 0) groups.push({ name: c.name, items });
    });
    const remaining = apps.filter((a) => !categories.some((c) => c.id === a.category_id));
    if (remaining.length > 0) groups.push({ name: 'Other', items: remaining });
  } else if (groupBy === 'source') {
    ['host', 'docker', 'custom'].forEach((src) => {
      const items = apps.filter((a) => a.source.toLowerCase() === src);
      if (items.length > 0) groups.push({ name: src.toUpperCase(), items });
    });
  } else if (groupBy === 'status') {
    ['up', 'down', 'conflict'].forEach((st) => {
      const items = apps.filter((a) => a.status.toLowerCase() === st);
      if (items.length > 0) groups.push({ name: st.toUpperCase(), items });
    });
  } else {
    groups.push({ name: '', items: apps });
  }

  return (
    <div className="portly-table-wrap">
      <div className="portly-table-grid">
        {/* Table Header */}
        <div className="portly-table-header" style={{ gridTemplateColumns: gridCols }}>
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <input
              type="checkbox"
              aria-label="Select all"
              checked={allSelected}
              onChange={onSelectAll}
              className="c103"
              style={{ cursor: 'pointer' }}
            />
          </div>
          <div></div>
          <div style={{ color: 'var(--muted)' }}>Name</div>
          <div style={{ color: 'var(--accent)', display: hide(showPort) }}>Port</div>
          <div style={{ display: hide(showSource) }}>Source</div>
          <div>Category</div>
          <div style={{ display: hide(showBind) }}>Bind</div>
          <div>Status</div>
          <div style={{ display: hide(showCpuRam) }}>CPU</div>
          <div style={{ display: hide(showCpuRam) }}>RAM</div>
          <div style={{ display: hide(showUptime) }}>Uptime</div>
          <div style={{ textAlign: 'right' }}>Actions</div>
        </div>

        {/* Rows */}
        {apps.length === 0 ? (
          <EmptyState />
        ) : (
          groups.map((grp, grpIdx) => (
            <React.Fragment key={grpIdx}>
              {grp.name && (
                <div
                  style={{
                    padding: '8px 18px',
                    background: 'rgba(255, 255, 255, 0.03)',
                    fontSize: '12px',
                    fontWeight: 600,
                    color: 'var(--accent)',
                    letterSpacing: '0.04em',
                    borderTop: '1px solid rgba(255, 255, 255, 0.06)',
                    borderBottom: '1px solid rgba(255, 255, 255, 0.04)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                  }}
                >
                  <span>{grp.name}</span>
                  <span style={{ fontSize: '11px', color: 'var(--muted)' }}>({grp.items.length})</span>
                </div>
              )}

              {grp.items.map((app) => {
                const isSelected = selectedIds.includes(app.id);
                const catColor = getCategoryColor(app.category_id);
                const catName = getCategoryName(app.category_id);
                const cpuVal = app.cpu_percent == null ? null : Math.min(100, Math.max(0, app.cpu_percent));
                const statsStale = app.stats_age_sec == null || app.stats_age_sec > 15;

                return (
                  <div
                    key={app.id}
                    className={`portly-table-row ${isSelected ? 'selected' : ''}`}
                    tabIndex={0}
                    style={{ ...padStyle, gridTemplateColumns: gridCols }}
                    onClick={() => onOpenDetail(app)}
                    onKeyDown={(e) => {
                      if (e.target !== e.currentTarget) return;
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        onOpenDetail(app);
                      }
                    }}
                  >
                    {/* Checkbox */}
                    <div className="table-cell" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        aria-label={`Select ${app.name}`}
                        checked={isSelected}
                        onChange={() => onToggleSelect(app.id)}
                        className="c103"
                        style={{ cursor: 'pointer' }}
                      />
                    </div>

                    {/* Grab handle */}
                    <div className="table-cell" style={{ color: 'var(--muted)', cursor: 'grab' }}>
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <circle cx="9" cy="6" r="1"></circle>
                        <circle cx="15" cy="6" r="1"></circle>
                        <circle cx="9" cy="12" r="1"></circle>
                        <circle cx="15" cy="12" r="1"></circle>
                        <circle cx="9" cy="18" r="1"></circle>
                        <circle cx="15" cy="18" r="1"></circle>
                      </svg>
                    </div>

                    {/* Name & Process */}
                    <div className="table-cell" style={{ gap: '10px' }}>
                      <AppIcon appId={app.id} name={app.name} source={app.source} size={30} />
                      <div style={{ minWidth: 0, overflow: 'hidden' }}>
                        <button type="button" className="app-name-btn" style={{ fontWeight: 600, color: 'var(--text)', fontSize: '13.5px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {app.name}
                          {app.pinned && <span style={{ marginLeft: '6px', fontSize: '11px', color: 'var(--warning)' }}>★</span>}
                        </button>
                        <div style={{ fontSize: '11.5px', color: 'var(--muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {app.source === 'docker'
                            ? (app.image || app.container_name)
                            : (app.process_name ? `${app.process_name}${app.pid ? ` · PID ${app.pid}` : ''}` : app.cmdline || 'Host')}
                        </div>
                      </div>
                    </div>

                    {/* Port */}
                    <div className="table-cell" style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 600, color: 'var(--accent)', fontSize: '13.5px', display: hide(showPort) }}>
                      {app.port || '—'}
                    </div>

                    {/* Source Badge */}
                    <div className="table-cell" style={{ gap: '6px', display: hide(showSource) }}>
                      <span
                        style={{
                          fontSize: '11.5px',
                          lineHeight: '18px',
                          padding: '1px 8px',
                          borderRadius: '999px',
                          textTransform: 'capitalize',
                          fontWeight: 500,
                          color: app.source === 'docker' ? 'var(--success)' : '#C4B5FD',
                          background: app.source === 'docker' ? 'rgba(94, 234, 212, 0.12)' : 'rgba(196, 181, 253, 0.12)',
                          border: `1px solid ${app.source === 'docker' ? 'rgba(94, 234, 212, 0.25)' : 'rgba(196, 181, 253, 0.25)'}`,
                        }}
                      >
                        {app.source}
                      </span>
                      {app.url_override && (
                        <span
                          style={{
                            fontSize: '10.5px',
                            padding: '1px 6px',
                            borderRadius: '999px',
                            background: 'rgba(251, 191, 119, 0.15)',
                            color: 'var(--warning)',
                            border: '1px solid rgba(251, 191, 119, 0.25)',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                          }}
                          title={`Tunnel URL: ${app.url_override}`}
                        >
                          <Icon name="cloud" size={11} />
                          <span>Tunnel</span>
                        </span>
                      )}
                      {app.has_tls && (
                        <span
                          style={{
                            fontSize: '10px',
                            padding: '1px 6px',
                            borderRadius: '999px',
                            background: app.tls_expired
                              ? 'rgba(255, 92, 92, 0.18)'
                              : (app.tls_days_remaining !== undefined && app.tls_days_remaining <= 30)
                              ? 'rgba(251, 191, 119, 0.18)'
                              : 'rgba(94, 234, 212, 0.14)',
                            color: app.tls_expired
                              ? 'var(--danger)'
                              : (app.tls_days_remaining !== undefined && app.tls_days_remaining <= 30)
                              ? 'var(--warning)'
                              : 'var(--success)',
                            border: `1px solid ${
                              app.tls_expired
                                ? 'rgba(255, 92, 92, 0.3)'
                                : (app.tls_days_remaining !== undefined && app.tls_days_remaining <= 30)
                                ? 'rgba(251, 191, 119, 0.3)'
                                : 'rgba(94, 234, 212, 0.25)'
                            }`,
                          }}
                          title={
                            app.tls_expired
                              ? 'TLS Certificate Expired!'
                              : app.tls_days_remaining !== undefined
                              ? `TLS valid for ${app.tls_days_remaining} days`
                              : 'TLS / SSL Enabled'
                          }
                        >
                          {app.tls_expired ? <><Icon name="x" size={12} color="var(--danger)" /> Expired</> : (app.tls_days_remaining !== undefined && app.tls_days_remaining <= 30) ? <><Icon name="warning" size={12} color="var(--warning)" /> {app.tls_days_remaining}d</> : <><Icon name="lock" size={12} /> TLS</>}
                        </span>
                      )}
                    </div>

                    {/* Category Badge */}
                    <div className="table-cell" style={{ gap: '6px' }}>
                      <span
                        className="table-cat-badge cat-text"
                        style={{
                          borderColor: `${catColor}35`,
                          background: `${catColor}14`,
                          '--cat-color': catColor,
                        } as React.CSSProperties}
                        title={catName}
                      >
                        {catName}
                      </span>
                      {app.category_mode === 'manual' && (
                        <span style={{ fontSize: '10px', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                          M
                        </span>
                      )}
                    </div>

                    {/* Bind Address (No collision with status) */}
                    <div className="table-cell" style={{ display: hide(showBind) }}>
                      <div className="table-bind-text">
                        <span>{app.bind}</span>
                        {app.local_only && (
                          <span className="table-local-tag" title="Loopback only (not accessible from LAN)">
                            Local
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Status */}
                    <div className="table-cell">
                      <div className="table-status">
                        {app.status === 'up' && (
                          <>
                            <span className="status-dot-up"></span>
                            <span style={{ color: 'var(--text)' }}>Up</span>
                          </>
                        )}
                        {app.status === 'down' && (
                          <>
                            <span className="status-dot-down"></span>
                            <span style={{ color: 'var(--danger)' }}>Down</span>
                          </>
                        )}
                        {app.status === 'conflict' && (
                          <>
                            <span className="status-dot-conflict"></span>
                            <span style={{ color: 'var(--warning)' }}>Conflict</span>
                          </>
                        )}
                        {app.status === 'unknown' && (
                          <>
                            <span className="status-dot-unknown"></span>
                            <span style={{ color: 'var(--muted)' }}>Unknown</span>
                          </>
                        )}
                      </div>
                    </div>

                    {/* CPU bar */}
                    <div className="table-cell" style={{ gap: '8px', display: hide(showCpuRam) }}>
                      <div style={{ width: '42px', height: '4px', borderRadius: '2px', background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
                        <div style={{ width: `${cpuVal === null ? 0 : Math.max(4, cpuVal)}%`, height: '100%', background: 'var(--accent)', borderRadius: '2px' }} />
                      </div>
                      <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '11px', color: 'var(--muted)' }} title={statsStale ? 'Stale or unavailable stats' : undefined}>
                        {cpuVal === null ? '—' : `${cpuVal}%`}{statsStale ? '*' : ''}
                      </span>
                    </div>

                    {/* RAM */}
                    <div className="table-cell" style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '12px', color: 'var(--muted)', display: hide(showCpuRam) }} title={statsStale ? 'Stale or unavailable stats' : undefined}>
                      {app.ram_mb == null ? '—' : app.ram_mb > 0 ? `${app.ram_mb} MB` : '0 MB'}
                    </div>

                    {/* Uptime */}
                    <div className="table-cell" style={{ fontSize: '12px', color: 'var(--muted)', display: hide(showUptime) }}>
                      {app.uptime_sec == null ? '—' : app.uptime_sec >= 86400
                        ? `${Math.floor(app.uptime_sec / 86400)}d ${Math.floor((app.uptime_sec % 86400) / 3600)}h`
                        : app.uptime_sec >= 3600
                        ? `${Math.floor(app.uptime_sec / 3600)}h ${Math.floor((app.uptime_sec % 3600) / 60)}m`
                        : `${Math.floor(app.uptime_sec / 60)}m`}
                    </div>

                    {/* Actions */}
                    <div className="table-cell" style={{ justifyContent: 'flex-end', gap: '6px' }} onClick={(e) => e.stopPropagation()}>
                      {!readOnly && (app.status === 'up' ? (
                        <button
                          type="button"
                          className="row-action-btn"
                          aria-label={`Stop ${app.name}`}
                          title={safeMode ? 'Safe mode is ON (locked)' : `Stop ${app.name}`}
                          onClick={(e) => onQuickStop(app, e)}
                        >
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <rect x="6" y="6" width="12" height="12" rx="2"></rect>
                          </svg>
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="row-action-btn"
                          aria-label={`Start ${app.name}`}
                          title={safeMode ? 'Safe mode is ON (locked)' : `Start ${app.name}`}
                          onClick={(e) => onQuickStart(app, e)}
                        >
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <path d="M7 5v14l12-7z"></path>
                          </svg>
                        </button>
                      ))}

                      <button
                        type="button"
                        className="row-action-btn"
                        aria-label={`Logs for ${app.name}`}
                        title="View live logs"
                        onClick={(e) => onQuickLogs(app, e)}
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"></path>
                        </svg>
                      </button>

                      {!readOnly && app.source === 'host' && onAdoptApp && (
                        <button
                          type="button"
                          className="row-action-btn"
                          aria-label={`Adopt ${app.name} as Custom App`}
                          title="Adopt this host process as a Portly-managed Custom App"
                          onClick={(e) => {
                            e.stopPropagation();
                            onAdoptApp(app);
                          }}
                          style={{ color: 'var(--accent)' }}
                        >
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
                          </svg>
                        </button>
                      )}

                      <button
                        type="button"
                        className="row-action-btn"
                        aria-label={`Details for ${app.name}`}
                        title="Open configuration & details"
                        onClick={() => onOpenDetail(app)}
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <circle cx="5" cy="12" r="1.5"></circle>
                          <circle cx="12" cy="12" r="1.5"></circle>
                          <circle cx="19" cy="12" r="1.5"></circle>
                        </svg>
                      </button>
                    </div>
                  </div>
                );
              })}
            </React.Fragment>
          ))
        )}
      </div>
    </div>
  );
};
