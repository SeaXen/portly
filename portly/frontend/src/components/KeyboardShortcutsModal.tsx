import React from 'react';

interface KeyboardShortcutsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const KeyboardShortcutsModal: React.FC<KeyboardShortcutsModalProps> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;

  const shortcuts = [
    { key: '/', desc: 'Quick focus search input' },
    { key: 'Ctrl + K / ⌘ + K', desc: 'Open Command Palette' },
    { key: 'g then t', desc: 'Switch to Table view' },
    { key: 'g then g', desc: 'Switch to Grid (tiles) view' },
    { key: 'g then b', desc: 'Switch to Board (Kanban) view' },
    { key: 'g then l', desc: 'Switch to List view' },
    { key: 'Esc', desc: 'Close any open modal, dialog, or drawer' },
    { key: '?', desc: 'Show this keyboard shortcuts cheatsheet' },
  ];

  return (
    <div className="modal-backdrop" onClick={onClose} style={{ zIndex: 1400 }}>
      <div
        className="modal-content"
        style={{
          width: '460px',
          background: '#101218',
          border: '1px solid rgba(255,255,255,0.12)',
          borderRadius: '16px',
          padding: '24px',
          boxSizing: 'border-box',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '18px', borderBottom: '1px solid rgba(255,255,255,0.07)', paddingBottom: '12px' }}>
          <h3 style={{ margin: 0, fontSize: '17px', fontWeight: 600, color: '#ECEEF3' }}>Keyboard Shortcuts</h3>
          <button type="button" className="c077" onClick={onClose} aria-label="Close">✕</button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {shortcuts.map((s, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '8px 12px',
                background: '#151821',
                borderRadius: '8px',
                fontSize: '13px',
              }}
            >
              <span style={{ color: '#8D95A5' }}>{s.desc}</span>
              <kbd
                style={{
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: '12px',
                  background: 'rgba(255,255,255,0.08)',
                  padding: '3px 8px',
                  borderRadius: '6px',
                  color: '#8C9EFF',
                }}
              >
                {s.key}
              </kbd>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
