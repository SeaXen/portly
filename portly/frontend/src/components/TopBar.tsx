import React, { useState } from 'react';
import { api } from '../api';

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
}) => {
  const [showExportMenu, setShowExportMenu] = useState(false);
  const [scanning, setScanning] = useState(false);

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
        <label className="c074" style={{ cursor: 'text' }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ color: '#8D95A5' }}>
            <circle cx="11" cy="11" r="7"></circle>
            <path d="m20 20-3.5-3.5"></path>
          </svg>
          <input
            type="text"
            placeholder="Search ports, apps, containers…"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            className="c075"
            autoComplete="off"
            spellCheck={false}
          />
          <kbd
            className="c076"
            onClick={onOpenCommandPalette}
            style={{ cursor: 'pointer' }}
            title="Press Ctrl+K or Cmd+K"
          >
            Ctrl K
          </kbd>
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
            className="c077"
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
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: '#8C9EFF' }}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="8" y1="13" x2="16" y2="13"></line><line x1="8" y1="17" x2="16" y2="17"></line></svg> CSV Table
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
                  transition: 'background 0.1s',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.06)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                onClick={() => setShowExportMenu(false)}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: '#5EEAD4' }}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg> Markdown Sheet
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
                  transition: 'background 0.1s',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.06)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                onClick={() => setShowExportMenu(false)}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: '#FBBF77' }}><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path><polyline points="17 21 17 13 7 13 7 21"></polyline><polyline points="7 3 7 8 15 8"></polyline></svg> Full JSON Backup
              </a>
            </div>
          )}
        </div>

        {/* Scan Now Button (Utility) */}
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
            transition: 'all 0.15s',
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
          {scanning ? 'Scanning…' : 'Scan now'}
        </button>

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
    </div>
  );
};
