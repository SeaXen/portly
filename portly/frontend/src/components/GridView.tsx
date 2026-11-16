import React from 'react';
import { AppItem, Category } from '../types';
import { AppIcon } from './AppIcon';

interface GridViewProps {
  apps: AppItem[];
  onOpenDetail: (app: AppItem) => void;
  categories: Category[];
  visibleFields?: Record<string, boolean>;
}

export const GridView: React.FC<GridViewProps> = ({ apps, onOpenDetail, categories, visibleFields = {} }) => {
  return (
    <div className="c025" style={{ width: '100%', boxSizing: 'border-box' }}>
      {apps.map((app) => {
        const initial = (app.name || 'A').charAt(0).toUpperCase();

        return (
          <div
            key={app.id}
            role="button"
            tabIndex={0}
            aria-label={`View details for ${app.name}`}
            className="c026"
            style={{
              cursor: 'pointer',
              transition: 'border-color 0.15s, transform 0.1s',
            }}
            onClick={() => onOpenDetail(app)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onOpenDetail(app);
              }
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'rgba(140, 158, 255, 0.4)';
              e.currentTarget.style.transform = 'translateY(-2px)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = '#242C37';
              e.currentTarget.style.transform = 'translateY(0)';
            }}
          >
            {/* Top row */}
            <div className="c027">
              <AppIcon appId={app.id} name={app.name} source={app.source} size={36} className="c028" />
              <div className="c029">
                <div className="c030" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {app.name}
                </div>
                <div className="c013" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {app.source === 'docker' ? (app.image || app.container_name) : (app.process_name || app.cmdline || 'Host')}
                </div>
              </div>
              <div className="c031">
                <span
                  className="c032"
                  style={{
                    backgroundColor: app.status === 'up' ? '#4ADE80' : (app.status === 'down' ? '#F87171' : '#FBBF77'),
                  }}
                />
                <span style={{ textTransform: 'capitalize' }}>{app.status}</span>
              </div>
            </div>

            {/* Middle row: Big Port */}
            <div className="c033">
              <div className="c034">:{app.port}</div>
              <div className="c035">
                {visibleFields.source !== false && (
                  <span className={app.source === 'docker' ? 'c040' : 'c036'} style={{ textTransform: 'capitalize' }}>
                    {app.source}
                  </span>
                )}
                {(app.url_override || (app.open_url && !app.open_url.includes('localhost'))) && (
                  <span
                    style={{
                      fontSize: '11px',
                      padding: '1px 7px',
                      borderRadius: '6px',
                      background: 'rgba(251, 191, 119, 0.15)',
                      color: '#FBBF77',
                      border: '1px solid rgba(251, 191, 119, 0.25)',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '3px',
                    }}
                    title={app.url_override || app.open_url}
                  >
                    <span>☁</span>
                    <span>Tunnel</span>
                  </span>
                )}
                {visibleFields.bind !== false && <span className="c037">{app.bind}</span>}
              </div>
            </div>

            {/* Bottom row: CPU & RAM, Open */}
            <div className="c038">
              {visibleFields.cpuram !== false ? (
                <span>
                  CPU {app.cpu_percent || 0}% &nbsp;·&nbsp; RAM {app.ram_mb || 0} MB
                </span>
              ) : <span />}
              {app.open_url ? (
                <a
                  href={app.open_url}
                  target="_blank"
                  rel="noreferrer"
                  className="c039"
                  onClick={(e) => e.stopPropagation()}
                >
                  Open ↗
                </a>
              ) : (
                <span className="c039">Details</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};
