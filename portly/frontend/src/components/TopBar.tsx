import React, { useRef, useState } from 'react';
import { api } from '../api';
import { ConfirmDialog } from './ConfirmDialog';
import { useToast } from './Toast';

interface TopBarProps {
  title: string;
  search: string;
  onSearchChange: (val: string) => void;
  onOpenCommandPalette: () => void;
  onOpenAddApp: () => void;
  onTriggerScan: () => void;
  theme: string;
  onToggleTheme: () => void;
  lastScanTime: number;
  kioskMode?: boolean;
  onToggleKiosk?: () => void;
  user?: any;
  onOpenUserManagement?: () => void;
  onLogout?: () => void;
  readOnly?: boolean;
}

export const TopBar: React.FC<TopBarProps> = ({
  title,
  search,
  onSearchChange,
  onOpenCommandPalette,
  onOpenAddApp,
  onTriggerScan,
  theme,
  onToggleTheme,
  lastScanTime,
  kioskMode,
  onToggleKiosk,
  user,
  onOpenUserManagement,
  onLogout,
  readOnly = false,
}) => {
  const [showExportMenu, setShowExportMenu] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [pendingBackup, setPendingBackup] = useState<any>(null);
  const [showRestoreConfirm, setShowRestoreConfirm] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { success, error } = useToast();

  const handleImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    file.text().then((text) => {
      setPendingBackup(JSON.parse(text));
      setShowRestoreConfirm(true);
    }).catch((err: any) => error(`Restore failed: Invalid backup file (${err.message})`));
  };

  const resetFileInput = () => {
    if (fileInputRef.current) fileInputRef.current.value = '';
    setPendingBackup(null);
    setShowRestoreConfirm(false);
  };

  const confirmRestore = async () => {
    const backup = pendingBackup;
    resetFileInput();
    if (!backup) return;
    try {
      await api.importBackup(backup);
      success('Backup restored successfully. Reloading…');
      setTimeout(() => window.location.reload(), 600);
    } catch (err: any) {
      error(`Restore failed: ${err.message}`);
    }
  };

  const secondsAgo = lastScanTime > 0 ? Math.max(1, Math.round((Date.now() / 1000) - lastScanTime)) : 1;

  const handleScan = async () => {
    setScanning(true);
    try {
      await onTriggerScan();
    } finally {
      setTimeout(() => setScanning(false), 600);
    }
  };

  return (
    <div className="c068" style={{ width: '100%' }}>
      {/* Title & Live Status */}
      <div className="c069">
        <h1 className="c070">{title}</h1>
        <span className="c071">
          <span className="live-dot" style={{ marginRight: '6px' }} />
          Live · {secondsAgo}s ago
        </span>
      </div>

      {/* Search & Actions */}
      <div className="c073" style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <button
          type="button"
          className="c077 topbar-search-compact"
          aria-label="Search ports, apps, containers"
          title="Search (Ctrl+K)"
          onClick={onOpenCommandPalette}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="7"></circle>
            <path d="m20 20-3.5-3.5"></path>
          </svg>
        </button>

        <label className="c074 topbar-search-label" style={{ cursor: 'text' }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ color: '#8D95A5' }}>
            <circle cx="11" cy="11" r="7"></circle>
            <path d="m20 20-3.5-3.5"></path>
          </svg>
          <input
            type="text"
            name="search"
            aria-label="Search ports, apps, containers"
            placeholder="Search ports, apps, containers…"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            className="c075"
            autoComplete="off"
            spellCheck={false}
          />
          <button
            type="button"
            className="c076"
            onClick={onOpenCommandPalette}
            style={{ cursor: 'pointer', background: 'transparent', color: '#8D95A5' }}
            title="Press Ctrl+K or Cmd+K"
          >
            Ctrl&nbsp;K
          </button>
        </label>

        {/* Theme Toggle */}
        <button
          type="button"
          className="c077"
          aria-label="Toggle theme"
          onClick={onToggleTheme}
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          style={{ width: '36px', height: '36px', borderRadius: '9px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
        >
          {theme === 'dark' ? (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M21 13A9 9 0 1 1 11 3a7 7 0 0 0 10 10z"></path>
            </svg>
          ) : (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="5"></circle>
              <line x1="12" y1="1" x2="12" y2="3"></line>
              <line x1="12" y1="21" x2="12" y2="23"></line>
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
              <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
              <line x1="1" y1="12" x2="3" y2="12"></line>
              <line x1="21" y1="12" x2="23" y2="12"></line>
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
              <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
            </svg>
          )}
        </button>

        {/* Kiosk Mode Toggle */}
        {onToggleKiosk && (
          <button
            type="button"
            className="c077 topbar-kiosk"
            aria-label="Toggle Kiosk mode"
            onClick={onToggleKiosk}
            title={kioskMode ? 'Exit Kiosk Mode (Shift+K)' : 'Kiosk / Wall Display Mode (Shift+K)'}
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '9px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: kioskMode ? '#5EEAD4' : 'inherit',
              borderColor: kioskMode ? 'rgba(94, 234, 212, 0.3)' : undefined,
            }}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
              <line x1="8" y1="21" x2="16" y2="21"></line>
              <line x1="12" y1="17" x2="12" y2="21"></line>
            </svg>
          </button>
        )}

        {/* Export Button with Dropdown */}
        {!readOnly && (
        <div style={{ position: 'relative' }}>
          <button
            type="button"
            className="c078"
            onClick={() => setShowExportMenu(!showExportMenu)}
            style={{ height: '36px', padding: '0 12px', gap: '6px', fontSize: '13px' }}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 4v11M7 11l5 5 5-5M4 20h16"></path>
            </svg>
            Export
          </button>

          {showExportMenu && (
            <div
              style={{
                position: 'absolute',
                top: '42px',
                right: 0,
                background: '#151821',
                border: '1px solid rgba(255,255,255,0.12)',
                borderRadius: '10px',
                padding: '6px',
                zIndex: 100,
                boxShadow: '0 12px 32px rgba(0,0,0,0.6)',
                minWidth: '170px',
                display: 'flex',
                flexDirection: 'column',
                gap: '2px',
              }}
              onMouseLeave={() => setShowExportMenu(false)}
            >
              <a
                href={api.exportUrl('csv')}
                download="portly-ports.csv"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '8px 12px',
                  borderRadius: '6px',
                  color: '#ECEEF3',
                  fontSize: '13px',
                  textDecoration: 'none',
                  transition: 'background 0.1s',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.06)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                onClick={() => setShowExportMenu(false)}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ color: '#8C9EFF' }}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="8" y1="13" x2="16" y2="13"></line><line x1="8" y1="17" x2="16" y2="17"></line></svg> CSV Table
              </a>
              <a
                href={api.exportUrl('markdown')}
                download="portly-ports.md"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '8px 12px',
                  borderRadius: '6px',
                  color: '#ECEEF3',
                  fontSize: '13px',
                  textDecoration: 'none',
                  transition: 'background-color 0.1s',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.06)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                onClick={() => setShowExportMenu(false)}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ color: '#5EEAD4' }}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg> Markdown Sheet
              </a>
              <a
                href={api.exportUrl('json')}
                download="portly-backup.json"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '8px 12px',
                  borderRadius: '6px',
                  color: '#ECEEF3',
                  fontSize: '13px',
                  textDecoration: 'none',
                  transition: 'background-color 0.1s',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.06)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                onClick={() => setShowExportMenu(false)}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ color: '#FBBF77' }}><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path><polyline points="17 21 17 13 7 13 7 21"></polyline><polyline points="7 3 7 8 15 8"></polyline></svg> Full JSON Backup
              </a>
              <input
                ref={fileInputRef}
                type="file"
                accept="application/json,.json"
                onChange={handleImport}
                style={{ display: 'none' }}
                aria-label="Restore backup file"
              />
              <button
                type="button"
                style={{
                  display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 12px',
                  borderRadius: '6px', color: '#ECEEF3', fontSize: '13px',
                  background: 'transparent', border: 'none', cursor: 'pointer', width: '100%', textAlign: 'left',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.06)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                onClick={() => { setShowExportMenu(false); fileInputRef.current?.click(); }}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ color: '#5EEAD4' }}><path d="M12 4v11M7 11l5 5 5-5M4 20h16"></path></svg> Restore Backup
              </button>
            </div>
          )}
        </div>
        )}

        {/* Scan Now Button (Utility) */}
        {!readOnly && (
        <button
          type="button"
          onClick={handleScan}
          disabled={scanning}
          style={{
            height: '36px',
            padding: '0 12px',
            borderRadius: '9px',
            background: 'rgba(255,255,255,0.05)',
            border: '1px solid rgba(255,255,255,0.09)',
            color: '#ECEEF3',
            fontSize: '13px',
            fontWeight: 500,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            cursor: scanning ? 'not-allowed' : 'pointer',
            transition: 'background-color 0.15s, border-color 0.15s',
          }}
          onMouseEnter={(e) => {
            if (!scanning) e.currentTarget.style.background = 'rgba(255,255,255,0.09)';
          }}
          onMouseLeave={(e) => {
            if (!scanning) e.currentTarget.style.background = 'rgba(255,255,255,0.05)';
          }}
          title="Rescan sockets and Docker containers"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
            style={{
              animation: scanning ? 'spin 1s linear infinite' : 'none',
              color: '#8C9EFF',
            }}
          >
            <path d="M21 12a9 9 0 1 1-3-6.7"></path>
            <path d="M21 4v5h-5"></path>
          </svg>
          <span className="topbar-scan-label">{scanning ? 'Scanning…' : 'Scan Now'}</span>
        </button>
        )}

        {/* Users & Audit Button for Admins */}
        {user?.role === 'admin' && onOpenUserManagement && (
          <button
            type="button"
            onClick={onOpenUserManagement}
            title="User Management & Audit Logs"
            style={{
              height: '36px',
              padding: '0 12px',
              borderRadius: '9px',
              background: 'rgba(140, 158, 255, 0.1)',
              border: '1px solid rgba(140, 158, 255, 0.3)',
              color: '#8C9EFF',
              fontSize: '13px',
              fontWeight: 500,
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              cursor: 'pointer',
            }}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
              <circle cx="9" cy="7" r="4"></circle>
              <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
              <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
            </svg>
            <span className="topbar-users-label">Users &amp; Audit</span>
          </button>
        )}

        {/* User Info & Sign Out */}
        {user && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', paddingLeft: '4px' }}>
            <span
              className="topbar-user-badge"
              style={{
                fontSize: '12px',
                color: '#8D95A5',
                background: 'rgba(255,255,255,0.05)',
                padding: '4px 10px',
                borderRadius: '6px',
                border: '1px solid rgba(255,255,255,0.08)',
              }}
            >
              {user.username} <span style={{ color: user.role === 'admin' ? '#8C9EFF' : '#5EEAD4', marginLeft: 4 }}>({user.role})</span>
            </span>
            {onLogout && (
              <button
                type="button"
                onClick={onLogout}
                title="Sign Out"
                aria-label="Sign Out"
                style={{
                  height: '36px',
                  width: '36px',
                  borderRadius: '9px',
                  background: 'rgba(255,255,255,0.05)',
                  border: '1px solid rgba(255,255,255,0.08)',
                  color: '#8D95A5',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                }}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                  <polyline points="16 17 21 12 16 7"></polyline>
                  <line x1="21" y1="12" x2="9" y2="12"></line>
                </svg>
              </button>
            )}
          </div>
        )}

        {/* Add App Button (Primary Hero Action) */}
        <button
          type="button"
          onClick={onOpenAddApp}
          style={{
            height: '36px',
            padding: '0 16px',
            borderRadius: '9px',
            background: '#8C9EFF',
            border: 0,
            color: '#0A0D14',
            fontSize: '13.5px',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            cursor: 'pointer',
            boxShadow: '0 2px 10px rgba(140, 158, 255, 0.3)',
            transition: 'transform 0.1s, box-shadow 0.15s',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.transform = 'translateY(-1px)';
            e.currentTarget.style.boxShadow = '0 4px 14px rgba(140, 158, 255, 0.45)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = 'translateY(0)';
            e.currentTarget.style.boxShadow = '0 2px 10px rgba(140, 158, 255, 0.3)';
          }}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 5v14M5 12h14"></path>
          </svg>
          Add app
        </button>
      </div>

      <ConfirmDialog
        isOpen={showRestoreConfirm}
        title="Restore Backup?"
        message="Restoring will overwrite existing data with the selected backup. Sections applied: categories, rules, custom apps, views, app overrides, and settings."
        confirmLabel="Restore Backup"
        isDanger={true}
        onConfirm={confirmRestore}
        onCancel={resetFileInput}
      />
    </div>
  );
};
