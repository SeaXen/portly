import React, { useState } from 'react';
import { ViewItem } from '../types';

interface SavedViewTabsProps {
  views: ViewItem[];
  activeViewId: string;
  onSelectView: (viewId: string) => void;
  onSaveCurrentView: (name: string) => void;
  appsCount: number;
  devCount: number;
  exposedCount: number;
  dockerCount: number;
}

export const SavedViewTabs: React.FC<SavedViewTabsProps> = ({
  views,
  activeViewId,
  onSelectView,
  onSaveCurrentView,
  appsCount,
  devCount,
  exposedCount,
  dockerCount,
}) => {
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [newViewName, setNewViewName] = useState('');

  const getCountForView = (id: string) => {
    if (id === 'all') return appsCount;
    if (id === 'dev') return devCount;
    if (id === 'exposed') return exposedCount;
    if (id === 'docker') return dockerCount;
    return undefined;
  };

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newViewName.trim()) return;
    onSaveCurrentView(newViewName.trim());
    setNewViewName('');
    setShowSaveModal(false);
  };

  const defaultViews: ViewItem[] = [
    { id: 'all', name: 'All Ports', filters: {}, sort: {}, group_by: 'none', view_type: 'table', columns: [] },
    { id: 'dev', name: 'Dev Only', filters: { category: 'development' }, sort: {}, group_by: 'none', view_type: 'table', columns: [] },
    { id: 'exposed', name: 'Exposed', filters: { bind: '0.0.0.0' }, sort: {}, group_by: 'none', view_type: 'table', columns: [] },
    { id: 'docker', name: 'Docker Only', filters: { source: 'docker' }, sort: {}, group_by: 'none', view_type: 'table', columns: [] },
  ];

  const allTabs = [
    ...defaultViews,
    ...views.filter((v) => !['all', 'dev', 'exposed', 'docker'].includes(v.id)),
  ];

  return (
    <>
      <div className="c089" style={{ width: '100%', borderBottom: '1px solid rgba(255, 255, 255, 0.07)', paddingBottom: '0', display: 'flex', alignItems: 'center', gap: '8px' }}>
        {allTabs.map((v) => {
          const isActive = activeViewId === v.id;
          const count = getCountForView(v.id);

          return (
            <button
              key={v.id}
              type="button"
              onClick={() => onSelectView(v.id)}
              style={{
                background: 'transparent',
                border: 'none',
                borderBottom: isActive ? '2px solid #8C9EFF' : '2px solid transparent',
                cursor: 'pointer',
                font: 'inherit',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                padding: '8px 12px 10px 12px',
                color: isActive ? '#ECEEF3' : '#8D95A5',
                fontWeight: isActive ? 600 : 500,
                fontSize: '13.5px',
                transition: 'color 0.12s ease, border-color 0.12s ease',
              }}
              onMouseEnter={(e) => {
                if (!isActive) e.currentTarget.style.color = '#ECEEF3';
              }}
              onMouseLeave={(e) => {
                if (!isActive) e.currentTarget.style.color = '#8D95A5';
              }}
            >
              <span>{v.name}</span>
              {count !== undefined && (
                <span
                  style={{
                    fontFamily: 'JetBrains Mono, monospace',
                    fontSize: '11px',
                    padding: '1px 6px',
                    borderRadius: '6px',
                    background: isActive ? 'rgba(140, 158, 255, 0.2)' : 'rgba(255, 255, 255, 0.05)',
                    color: isActive ? '#ECEEF3' : '#8D95A5',
                  }}
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}

        <button
          type="button"
          onClick={() => setShowSaveModal(true)}
          style={{
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
            font: 'inherit',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '8px 12px 10px 12px',
            color: 'var(--muted)',
            fontSize: '13px',
            fontWeight: 500,
            marginLeft: 'auto',
            transition: 'color 0.12s',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.color = '#8C9EFF')}
          onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--muted)')}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 5v14M5 12h14"></path>
          </svg>
          Save View
        </button>
      </div>

      {showSaveModal && (
        <div className="modal-backdrop" onClick={() => setShowSaveModal(false)}>
          <div className="modal-content" style={{ width: '380px', background: '#101218', border: '1px solid rgba(255,255,255,0.12)', borderRadius: '14px', padding: '24px' }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 8px 0', fontSize: '16px', fontWeight: 600, color: '#ECEEF3' }}>Save Current View</h3>
            <p style={{ fontSize: '13px', color: '#8D95A5', margin: '0 0 16px 0', lineHeight: 1.5 }}>
              Save current filters, sort order, and column visibility as a tab.
            </p>
            <form onSubmit={handleSave}>
              <input
                type="text"
                name="viewName"
                aria-label="View name"
                autoComplete="off"
                placeholder="View name (e.g. Backend only)"
                value={newViewName}
                onChange={(e) => setNewViewName(e.target.value)}
                autoFocus
                className="c220"
                style={{ width: '100%', marginBottom: '18px', boxSizing: 'border-box' }}
                required
              />
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button type="button" className="c078" onClick={() => setShowSaveModal(false)}>Cancel</button>
                <button type="submit" className="c080" style={{ background: '#8C9EFF', color: '#0A0D14', fontWeight: 600 }}>Save View</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
};
