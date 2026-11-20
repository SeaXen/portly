import React, { useState } from 'react';
import { AppItem, Category } from '../types';

interface BoardViewProps {
  apps: AppItem[];
  categories: Category[];
  onOpenDetail: (app: AppItem) => void;
  onMoveAppCategory: (appId: string, newCategoryId: string) => void;
  onNewCategoryClick: () => void;
  readOnly?: boolean;
}

export const BoardView: React.FC<BoardViewProps> = ({
  apps,
  categories,
  onOpenDetail,
  onMoveAppCategory,
  onNewCategoryClick,
  readOnly = false,
}) => {
  const [draggedAppId, setDraggedAppId] = useState<string | null>(null);
  const [activeDropCategory, setActiveDropCategory] = useState<string | null>(null);

  const handleDragStart = (e: React.DragEvent, appId: string) => {
    if (readOnly) { e.preventDefault(); return; }
    e.dataTransfer.setData('text/plain', appId);
    setDraggedAppId(appId);
  };

  const handleDragOver = (e: React.DragEvent, categoryId: string) => {
    if (readOnly) return;
    e.preventDefault();
    if (activeDropCategory !== categoryId) {
      setActiveDropCategory(categoryId);
    }
  };

  const handleDrop = (e: React.DragEvent, categoryId: string) => {
    if (readOnly) return;
    e.preventDefault();
    const appId = e.dataTransfer.getData('text/plain') || draggedAppId;
    if (appId) {
      onMoveAppCategory(appId, categoryId);
    }
    setDraggedAppId(null);
    setActiveDropCategory(null);
  };

  return (
    <div className="c147" style={{ width: '100%', overflowX: 'auto', paddingBottom: '16px' }}>
      <div className="c148" style={{ display: 'flex', flexWrap: 'wrap', gap: '16px' }}>
        {categories
          .filter((cat) => draggedAppId || apps.some((a) => a.category_id === cat.id))
          .map((cat) => {
          const categoryApps = apps.filter((a) => a.category_id === cat.id);
          const isTarget = activeDropCategory === cat.id;

          return (
            <div
              key={cat.id}
              className={`c149 ${isTarget ? 'drop-target' : ''}`}
              style={{
                flex: '1 1 260px',
                minWidth: '260px',
                maxWidth: '300px',
                flexShrink: 1,
                background: 'var(--surface-1)',
                border: isTarget ? '2px dashed var(--accent)' : '1px solid rgba(255,255,255,0.07)',
                borderRadius: '14px',
                padding: '14px',
                display: 'flex',
                flexDirection: 'column',
                gap: '12px',
                transition: 'border-color 0.15s, background-color 0.15s',
              }}
              onDragOver={(e) => handleDragOver(e, cat.id)}
              onDrop={(e) => handleDrop(e, cat.id)}
              onDragLeave={() => setActiveDropCategory(null)}
            >
              {/* Category Column Header */}
              <div className="c150" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span
                  style={{
                    width: '8px',
                    height: '8px',
                    borderRadius: '3px',
                    backgroundColor: cat.color || 'var(--accent)',
                  }}
                />
                <span className="c152" style={{ fontWeight: 600, color: 'var(--text)', flex: 1 }}>
                  {cat.name}
                </span>
                <span className="c055">{categoryApps.length}</span>
                <span className="c112" style={{ textTransform: 'capitalize' }}>
                  {cat.mode || 'auto'}
                </span>
              </div>

              {/* Cards */}
              {categoryApps.map((app) => (
                <div
                  key={app.id}
                  role="button"
                  tabIndex={0}
                  aria-label={`View details for ${app.name}`}
                  className="c153 draggable-card"
                  draggable={!readOnly}
                  onDragStart={(e) => handleDragStart(e, app.id)}
                  onClick={() => onOpenDetail(app)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      onOpenDetail(app);
                    }
                  }}
                  style={{
                    background: 'var(--surface-2)',
                    border: '1px solid rgba(255,255,255,0.07)',
                    borderRadius: '10px',
                    padding: '12px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '6px',
                  }}
                >
                  <div className="c110" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      {!readOnly && (
                        <span className="c104" style={{ cursor: 'grab' }}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <circle cx="9" cy="6" r="1"></circle>
                            <circle cx="15" cy="6" r="1"></circle>
                            <circle cx="9" cy="12" r="1"></circle>
                            <circle cx="15" cy="12" r="1"></circle>
                            <circle cx="9" cy="18" r="1"></circle>
                            <circle cx="15" cy="18" r="1"></circle>
                          </svg>
                        </span>
                      )}
                      <span className="c154" style={{ fontWeight: 600, color: 'var(--text)' }}>
                        {app.name}
                      </span>
                    </div>
                    <span
                      className="c122"
                      style={{
                        backgroundColor: app.status === 'unknown' ? 'var(--muted)' : (app.status === 'up' ? 'var(--success)' : (app.status === 'down' ? 'var(--danger)' : 'var(--warning)')),
                      }}
                    />
                  </div>

                  <div className="c155" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span className="c156" style={{ fontFamily: 'JetBrains Mono, monospace', color: 'var(--accent)', fontWeight: 600, fontSize: '15px' }}>
                      {app.port || '—'}
                    </span>
                    <span className={app.source === 'docker' ? 'c111' : 'c109'} style={{ textTransform: 'capitalize' }}>
                      {app.source}
                    </span>
                  </div>

                  <div className="c065" style={{ fontSize: '12px', color: app.stats_age_sec == null || app.stats_age_sec > 15 ? 'var(--muted)' : 'var(--muted)' }} title={app.stats_age_sec == null || app.stats_age_sec > 15 ? 'Stale or unavailable stats' : undefined}>
                    CPU {app.cpu_percent == null ? '—' : `${app.cpu_percent}%`} · RAM {app.ram_mb == null ? '—' : `${app.ram_mb} MB`}{app.stats_age_sec == null || app.stats_age_sec > 15 ? ' (stale)' : ''}
                  </div>
                </div>
              ))}

              {/* Drop target placeholder */}
              {!readOnly && (
                <div
                  className="c160"
                  style={{
                    border: '1px dashed rgba(255,255,255,0.1)',
                    borderRadius: '8px',
                    padding: '12px',
                    textAlign: 'center',
                    fontSize: '12px',
                    color: 'var(--muted)',
                    backgroundColor: isTarget ? 'rgba(140, 158, 255, 0.08)' : 'transparent',
                  }}
                >
                  Drop to move here
                </div>
              )}
            </div>
          );
        })}

        {/* Add category button at the end of the board */}
        {!readOnly && (
          <button
            type="button"
            aria-label="Add category"
            className="c163"
            onClick={onNewCategoryClick}
            style={{
              width: '60px',
              minHeight: '60px',
              alignSelf: 'flex-start',
              borderRadius: '14px',
              border: '1px dashed rgba(255,255,255,0.15)',
              background: 'transparent',
              color: 'var(--muted)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            title="Create a new category"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 5v14M5 12h14"></path>
            </svg>
          </button>
        )}
      </div>
    </div>
  );
};
