import React, { useState } from 'react';
import { Category } from '../types';

interface BulkActionBarProps {
  selectedCount: number;
  categories: Category[];
  onMoveToCategory: (categoryId: string) => void;
  onAddTag: (tag: string) => void;
  onPin: () => void;
  onHide: () => void;
  onStart: () => void;
  onStop: () => void;
  onRestart: () => void;
  onClear: () => void;
}

export const BulkActionBar: React.FC<BulkActionBarProps> = ({
  selectedCount,
  categories,
  onMoveToCategory,
  onAddTag,
  onPin,
  onHide,
  onStart,
  onStop,
  onRestart,
  onClear,
}) => {
  const [showMoveMenu, setShowMoveMenu] = useState(false);
  const [showTagPrompt, setShowTagPrompt] = useState(false);
  const [tagInput, setTagInput] = useState('');

  if (selectedCount === 0) return null;

  return (
    <div className="floating-bulk-bar">
      <span className="c144" style={{ fontSize: '13px', color: '#ECEEF3', marginRight: '6px' }}>
        <b>{selectedCount}</b> selected
      </span>

      {/* Move to category dropdown */}
      <div style={{ position: 'relative' }}>
        <button
          type="button"
          className="c079"
          onClick={() => setShowMoveMenu(!showMoveMenu)}
        >
          Move to category
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="m6 9 6 6 6-6"></path>
          </svg>
        </button>

        {showMoveMenu && (
          <div
            style={{
              position: 'absolute',
              bottom: '42px',
              left: 0,
              background: '#151821',
              border: '1px solid rgba(255,255,255,0.12)',
              borderRadius: '9px',
              padding: '6px',
              zIndex: 100,
              minWidth: '160px',
              boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
            }}
            onMouseLeave={() => setShowMoveMenu(false)}
          >
            {categories.map((c) => (
              <button
                key={c.id}
                type="button"
                className="c053"
                style={{ width: '100%', border: 0, background: 'transparent', textAlign: 'left', cursor: 'pointer', fontSize: '13px' }}
                onClick={() => {
                  onMoveToCategory(c.id);
                  setShowMoveMenu(false);
                }}
              >
                {c.name}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Add tag */}
      {showTagPrompt ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <input
            type="text"
            placeholder="Tag name"
            value={tagInput}
            onChange={(e) => setTagInput(e.target.value)}
            className="c220"
            style={{ width: '100px', height: '32px' }}
            autoFocus
          />
          <button
            type="button"
            className="c080"
            style={{ height: '32px', padding: '0 10px' }}
            onClick={() => {
              if (tagInput.trim()) onAddTag(tagInput.trim());
              setTagInput('');
              setShowTagPrompt(false);
            }}
          >
            Add
          </button>
          <button
            type="button"
            className="c078"
            style={{ height: '32px' }}
            onClick={() => setShowTagPrompt(false)}
          >
            ✕
          </button>
        </div>
      ) : (
        <button type="button" className="c078" onClick={() => setShowTagPrompt(true)}>
          Add tag
        </button>
      )}

      <button type="button" className="c078" onClick={onPin}>
        Pin
      </button>

      <button type="button" className="c078" onClick={onHide}>
        Hide
      </button>

      <button type="button" className="c078" onClick={onStart}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M7 5v14l12-7z"></path>
        </svg>
        Start
      </button>

      <button type="button" className="c078" onClick={onStop}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="6" y="6" width="12" height="12" rx="2"></rect>
        </svg>
        Stop
      </button>

      <button type="button" className="c078" onClick={onRestart}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21 12a9 9 0 1 1-3-6.7"></path>
          <path d="M21 4v5h-5"></path>
        </svg>
        Restart
      </button>

      <button type="button" className="c077" aria-label="Clear selection" title="Clear selection" onClick={onClear}>
        ✕
      </button>
    </div>
  );
};
