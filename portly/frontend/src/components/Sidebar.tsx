import React, { useState } from 'react';
import { Category } from '../types';
import { useFocusTrap } from '../hooks/useFocusTrap';

interface SidebarProps {
  activeNav: string;
  onSelectNav: (nav: string) => void;
  categories: Category[];
  selectedCategory: string | null;
  onSelectCategory: (catId: string | null) => void;
  onNewCategoryClick: () => void;
  conflictCount: number;
  safeMode: boolean;
  onToggleSafeMode: (newVal: boolean, autoRelockSec?: number) => void;
  unlockCountdown?: number | null;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeNav,
  onSelectNav,
  categories,
  selectedCategory,
  onSelectCategory,
  onNewCategoryClick,
  conflictCount,
  safeMode,
  onToggleSafeMode,
  unlockCountdown,
}) => {
  const [showSafeModeModal, setShowSafeModeModal] = useState(false);
  const [autoRelockDuration, setAutoRelockDuration] = useState<number>(300); // 5 minutes default
  const safeModalRef = useFocusTrap<HTMLDivElement>(showSafeModeModal, () => setShowSafeModeModal(false));

  const handleSafeModeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const targetVal = e.target.checked;
    if (!targetVal) {
      setShowSafeModeModal(true);
    } else {
      onToggleSafeMode(true);
    }
  };

  const confirmUnlockSafeMode = () => {
    setShowSafeModeModal(false);
    onToggleSafeMode(false, autoRelockDuration > 0 ? autoRelockDuration : undefined);
  };

  return (
    <>
      <aside className="portly-sidebar">
        {/* Brand */}
        <button
          type="button"
          className="sidebar-brand"
          onClick={() => { onSelectNav('ports'); onSelectCategory(null); }}
          title="Portly Dashboard"
        >
          <div className="sidebar-logo">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect x="4" y="5" width="16" height="14" rx="3"></rect>
              <circle cx="9" cy="12" r="1.5" fill="currentColor"></circle>
              <circle cx="15" cy="12" r="1.5" fill="currentColor"></circle>
            </svg>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ fontSize: '17px', fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.02em', lineHeight: 1.2 }}>
              Portly
            </div>
            <span style={{ fontSize: '10px', color: 'var(--muted)', fontWeight: 500, letterSpacing: '0.04em', textTransform: 'uppercase' }}>
              Dashboard
            </span>
          </div>
        </button>

        {/* Navigation */}
        <nav className="sidebar-nav">
          <button
            type="button"
            aria-label="Overview"
            className={`sidebar-nav-btn ${activeNav === 'overview' ? 'active' : ''}`}
            onClick={() => { onSelectNav('overview'); onSelectCategory(null); }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect x="3" y="3" width="7" height="7" rx="1.5"></rect>
              <rect x="14" y="3" width="7" height="7" rx="1.5"></rect>
              <rect x="3" y="14" width="7" height="7" rx="1.5"></rect>
              <rect x="14" y="14" width="7" height="7" rx="1.5"></rect>
            </svg>
            <span className="sidebar-btn-label">Overview</span>
          </button>

          <button
            type="button"
            aria-label="Ports"
            className={`sidebar-nav-btn ${activeNav === 'ports' && selectedCategory === null ? 'active' : ''}`}
            onClick={() => { onSelectNav('ports'); onSelectCategory(null); }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect x="3" y="4" width="18" height="16" rx="2"></rect>
              <path d="M3 10h18M3 15h18M9 4v16"></path>
            </svg>
            <span className="sidebar-btn-label">Ports</span>
          </button>

          <button
            type="button"
            aria-label="Docker"
            className={`sidebar-nav-btn ${activeNav === 'docker' ? 'active' : ''}`}
            onClick={() => { onSelectNav('docker'); onSelectCategory(null); }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M3 8l9-5 9 5v8l-9 5-9-5z"></path>
              <path d="M3 8l9 5 9-5M12 13v8"></path>
            </svg>
            <span className="sidebar-btn-label">Docker</span>
          </button>

          <button
            type="button"
            aria-label="Stacks"
            className={`sidebar-nav-btn ${activeNav === 'stacks' ? 'active' : ''}`}
            onClick={() => { onSelectNav('stacks'); onSelectCategory(null); }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
              <polyline points="2 17 12 22 22 17"></polyline>
              <polyline points="2 12 12 17 22 12"></polyline>
            </svg>
            <span className="sidebar-btn-label">Stacks</span>
          </button>

          <button
            type="button"
            aria-label="System"
            className={`sidebar-nav-btn ${activeNav === 'system' ? 'active' : ''}`}
            onClick={() => { onSelectNav('system'); }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M3 12h4l3-8 4 16 3-8h4"></path>
            </svg>
            <span className="sidebar-btn-label">System</span>
          </button>

          <button
            type="button"
            className={`sidebar-nav-btn ${activeNav === 'conflicts' ? 'active' : ''}`}
            onClick={() => { onSelectNav('conflicts'); onSelectCategory(null); }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 3l10 18H2z"></path>
              <path d="M12 10v4M12 17h.01"></path>
            </svg>
            <span className="sidebar-btn-label">Conflicts</span>
            {conflictCount > 0 && <span className="sidebar-conflict-badge">{conflictCount}</span>}
          </button>

          <button
            type="button"
            aria-label="History"
            className={`sidebar-nav-btn ${activeNav === 'history' ? 'active' : ''}`}
            onClick={() => { onSelectNav('history'); }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="9"></circle>
              <path d="M12 7v5l3 2"></path>
            </svg>
            <span className="sidebar-btn-label">History</span>
          </button>
        </nav>

        {/* Categories Section */}
        <div className="sidebar-cat-section">
          <div className="sidebar-cat-header">
            <span>CATEGORIES</span>
            <button
              type="button"
              className="sidebar-add-cat-icon"
              onClick={onNewCategoryClick}
              title="Create new category"
              aria-label="Create new category"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 5v14M5 12h14"></path>
              </svg>
            </button>
          </div>

          <div className="sidebar-cat-list">
            {categories.map((cat) => {
              const isSelected = selectedCategory === cat.id;
              const catColor = cat.color || 'var(--accent)';

              return (
                <button
                  key={cat.id}
                  type="button"
                  className={`sidebar-cat-btn ${isSelected ? 'active' : ''}`}
                  onClick={() => {
                    onSelectNav('ports');
                    onSelectCategory(isSelected ? null : cat.id);
                  }}
                >
                  <span
                    className="sidebar-cat-dot"
                    style={{
                      backgroundColor: catColor,
                      boxShadow: isSelected ? `0 0 8px ${catColor}80` : `0 0 4px ${catColor}40`,
                    }}
                  />
                  <span className="sidebar-cat-name">{cat.name}</span>
                  <span className="sidebar-cat-count">{cat.count || 0}</span>
                  <span className="sidebar-cat-mode">{cat.mode || 'auto'}</span>
                </button>
              );
            })}
          </div>

          <button
            type="button"
            className="sidebar-new-cat-btn"
            onClick={onNewCategoryClick}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 5v14M5 12h14"></path>
            </svg>
            <span>New Category</span>
          </button>
        </div>

        {/* Safe Mode Switch Card */}
        <div className="sidebar-safe-card">
          <div className="safe-card-header">
            <span
              className="safe-card-icon"
              style={{
                color: safeMode ? 'var(--success)' : 'var(--danger)',
                background: safeMode ? 'rgba(94, 234, 212, 0.12)' : 'rgba(255, 138, 138, 0.12)',
              }}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                {safeMode ? (
                  <>
                    <rect x="4" y="11" width="16" height="10" rx="2"></rect>
                    <path d="M8 11V7a4 4 0 0 1 8 0v4"></path>
                  </>
                ) : (
                  <>
                    <rect x="4" y="11" width="16" height="10" rx="2"></rect>
                    <path d="M8 11V7a4 4 0 0 1 8 0"></path>
                  </>
                )}
              </svg>
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)' }}>
                Safe Mode
              </div>
              <div style={{ fontSize: '11px', color: safeMode ? 'var(--muted)' : 'var(--danger)', lineHeight: 1.3 }}>
                {safeMode
                  ? 'Mutations locked'
                  : unlockCountdown != null
                  ? `Re-locks in ${Math.floor(unlockCountdown / 60)}m ${unlockCountdown % 60}s`
                  : 'Actions unlocked (LIVE)'}
              </div>
            </div>
            <label className="portly-toggle">
              <input
                type="checkbox"
                aria-label="Toggle Safe Mode"
                checked={safeMode}
                onChange={handleSafeModeChange}
              />
              <span className="toggle-slider"></span>
            </label>
          </div>
        </div>
      </aside>

      {/* Confirmation Modal for unlocking safe mode */}
      {showSafeModeModal && (
        <div className="modal-backdrop" onClick={() => setShowSafeModeModal(false)}>
          <div
            ref={safeModalRef}
            className="modal-content"
            role="dialog"
            aria-modal="true"
            aria-label="Disable Safe Mode"
            style={{
              width: '440px',
              background: 'var(--surface-1)',
              border: '1px solid rgba(255,255,255,0.12)',
              borderRadius: '14px',
              padding: '24px',
            }}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                e.stopPropagation();
                setShowSafeModeModal(false);
              }
            }}
          >
            <div style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text)', marginBottom: '8px' }}>
              Disable Safe Mode?
            </div>
            <p style={{ fontSize: '13px', color: 'var(--muted)', lineHeight: 1.5, margin: '0 0 16px 0' }}>
              Turning off Safe mode allows executing real operations: starting/stopping services, killing processes, and recreating containers on your host machine.
            </p>

            <div style={{ background: 'var(--surface-input)', borderRadius: '10px', padding: '12px 16px', marginBottom: '20px', border: '1px solid var(--border-subtle)' }}>
              <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
                <legend style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text)', marginBottom: '8px', padding: 0 }}>Auto-Relock Protection</legend>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: 'var(--text)', cursor: 'pointer', marginBottom: '6px' }}>
                  <input
                    type="radio"
                    name="relock"
                    checked={autoRelockDuration === 300}
                    onChange={() => setAutoRelockDuration(300)}
                  />
                  Unlock for 5 minutes (Recommended)
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: 'var(--text)', cursor: 'pointer', marginBottom: '6px' }}>
                  <input
                    type="radio"
                    name="relock"
                    checked={autoRelockDuration === 900}
                    onChange={() => setAutoRelockDuration(900)}
                  />
                  Unlock for 15 minutes
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: 'var(--text)', cursor: 'pointer' }}>
                  <input
                    type="radio"
                    name="relock"
                    checked={autoRelockDuration === 0}
                    onChange={() => setAutoRelockDuration(0)}
                  />
                  Stay unlocked indefinitely
                </label>
              </fieldset>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button type="button" className="c078" onClick={() => setShowSafeModeModal(false)}>
                Keep Locked
              </button>
              <button
                type="button"
                className="c080"
                style={{ background: 'var(--danger)', color: 'var(--bg)', fontWeight: 600 }}
                onClick={confirmUnlockSafeMode}
              >
                Disable Safe Mode
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
