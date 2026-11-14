import React, { useEffect, useState } from 'react';
import { AppItem } from '../types';

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  apps: AppItem[];
  onSelectApp: (app: AppItem) => void;
  onTriggerScan: () => void;
  onSwitchView: (vt: 'table' | 'grid' | 'list' | 'board') => void;
  onOpenAddApp: () => void;
  onToggleSafeMode: () => void;
  safeMode: boolean;
}

type PaletteAction = {
  id: string;
  title: string;
  category: string;
  run: () => void;
};

type PaletteItem =
  | { type: 'action'; data: PaletteAction }
  | { type: 'app'; data: AppItem };

export const CommandPalette: React.FC<CommandPaletteProps> = ({
  isOpen,
  onClose,
  apps,
  onSelectApp,
  onTriggerScan,
  onSwitchView,
  onOpenAddApp,
  onToggleSafeMode,
  safeMode,
}) => {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [confirmDisableSafeMode, setConfirmDisableSafeMode] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      setConfirmDisableSafeMode(false);
      setQuery('');
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (isOpen) onClose();
        else setQuery('');
      } else if (e.key === 'Escape' && isOpen) {
        if (confirmDisableSafeMode) {
          setConfirmDisableSafeMode(false);
        } else {
          onClose();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose, confirmDisableSafeMode]);

  if (!isOpen) return null;

  const handleSafeModeAction = () => {
    if (safeMode) {
      setConfirmDisableSafeMode(true);
    } else {
      onToggleSafeMode();
      onClose();
    }
  };

  const actions: PaletteAction[] = [
    { id: 'act_scan', title: 'Trigger Immediate Port Scan', category: 'Action', run: () => { onTriggerScan(); onClose(); } },
    { id: 'act_add', title: 'Add Custom App / Container', category: 'Action', run: () => { onOpenAddApp(); onClose(); } },
    { id: 'act_safe', title: safeMode ? 'Disable Safe Mode (Unlock mutations)' : 'Enable Safe Mode (Lock mutations)', category: 'Security', run: handleSafeModeAction },
    { id: 'act_tbl', title: 'Switch to Table View', category: 'View', run: () => { onSwitchView('table'); onClose(); } },
    { id: 'act_grd', title: 'Switch to Grid View', category: 'View', run: () => { onSwitchView('grid'); onClose(); } },
    { id: 'act_brd', title: 'Switch to Board View', category: 'View', run: () => { onSwitchView('board'); onClose(); } },
    { id: 'act_lst', title: 'Switch to List View', category: 'View', run: () => { onSwitchView('list'); onClose(); } },
  ];

  const filteredApps = apps.filter(
    (a) =>
      a.name.toLowerCase().includes(query.toLowerCase()) ||
      String(a.port).includes(query) ||
      a.source.toLowerCase().includes(query.toLowerCase())
  ).slice(0, 8);

  const filteredActions = actions.filter((act) => act.title.toLowerCase().includes(query.toLowerCase()));

  const allItems: PaletteItem[] = [
    ...filteredActions.map((act) => ({ type: 'action' as const, data: act })),
    ...filteredApps.map((a) => ({ type: 'app' as const, data: a })),
  ];

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (confirmDisableSafeMode) {
      if (e.key === 'Enter') {
        e.preventDefault();
        onToggleSafeMode();
        setConfirmDisableSafeMode(false);
        onClose();
      }
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % Math.max(1, allItems.length));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 + allItems.length) % Math.max(1, allItems.length));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const current = allItems[selectedIndex];
      if (current) {
        if (current.type === 'action') {
          current.data.run();
        } else {
          onSelectApp(current.data);
          onClose();
        }
      }
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose} style={{ zIndex: 1300, alignItems: 'flex-start', paddingTop: '12vh' }}>
      <div className="command-palette" onClick={(e) => e.stopPropagation()}>
        {confirmDisableSafeMode ? (
          <div style={{ padding: '28px 24px', textAlign: 'center' }}>
            <div style={{ marginBottom: '12px', display: 'flex', justifyContent: 'center' }}>
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#FBBF77" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                <line x1="12" y1="9" x2="12" y2="13"></line>
                <line x1="12" y1="17" x2="12.01" y2="17"></line>
              </svg>
            </div>
            <div style={{ fontWeight: 600, fontSize: '16px', color: '#ECEEF3', marginBottom: '8px' }}>
              Unlock Safe Mode?
            </div>
            <div style={{ fontSize: '13px', color: '#8D95A5', marginBottom: '24px', lineHeight: 1.5, maxWidth: '420px', margin: '0 auto 24px' }}>
              Disabling Safe Mode allows mutating system actions including stopping, starting, restarting, killing host processes, and reassigning ports.
            </div>
            <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
              <button
                type="button"
                className="c078"
                onClick={() => setConfirmDisableSafeMode(false)}
              >
                Cancel (Keep Safe Mode ON)
              </button>
              <button
                type="button"
                style={{
                  background: '#FF5C5C',
                  color: '#FFFFFF',
                  border: 'none',
                  borderRadius: '8px',
                  padding: '8px 18px',
                  fontWeight: 600,
                  fontSize: '13px',
                  cursor: 'pointer',
                }}
                onClick={() => {
                  onToggleSafeMode();
                  setConfirmDisableSafeMode(false);
                  onClose();
                }}
              >
                Confirm Unlock (LIVE)
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="command-input-wrap">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ color: '#8D95A5' }}>
                <circle cx="11" cy="11" r="7"></circle>
                <path d="m20 20-3.5-3.5"></path>
              </svg>
              <input
                type="text"
                placeholder="Type a command, port, or service name..."
                value={query}
                onChange={(e) => { setQuery(e.target.value); setSelectedIndex(0); }}
                onKeyDown={handleKeyDown}
                autoFocus
                className="command-input"
              />
              <kbd className="c076">ESC</kbd>
            </div>

            <div className="command-results">
              {allItems.length === 0 ? (
                <div style={{ padding: '24px', textAlign: 'center', color: '#8D95A5', fontSize: '13px' }}>
                  No matching commands or services found.
                </div>
              ) : (
                allItems.map((item, idx) => {
                  const isSelected = idx === selectedIndex;
                  if (item.type === 'action') {
                    const act = item.data;
                    return (
                      <div
                        key={act.id}
                        className={`command-item ${isSelected ? 'active' : ''}`}
                        onClick={act.run}
                        onMouseEnter={() => setSelectedIndex(idx)}
                      >
                        <span>{act.title}</span>
                        <span className="command-badge">{act.category}</span>
                      </div>
                    );
                  } else {
                    const a = item.data;
                    return (
                      <div
                        key={a.id}
                        className={`command-item ${isSelected ? 'active' : ''}`}
                        onClick={() => { onSelectApp(a); onClose(); }}
                        onMouseEnter={() => setSelectedIndex(idx)}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <span style={{ fontWeight: 600 }}>{a.name}</span>
                          <span style={{ fontFamily: 'JetBrains Mono, monospace', color: '#8C9EFF' }}>:{a.port}</span>
                          <span style={{ fontSize: '12px', color: '#8D95A5' }}>{a.source}</span>
                        </div>
                        <span className="command-badge" style={{ color: a.status === 'up' ? '#5EEAD4' : '#FF8A8A' }}>
                          {a.status}
                        </span>
                      </div>
                    );
                  }
                })
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};
