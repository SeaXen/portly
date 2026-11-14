import React, { useState } from 'react';
import { Category } from '../types';

interface ToolbarProps {
  viewType: 'table' | 'grid' | 'list' | 'board';
  onChangeViewType: (vt: 'table' | 'grid' | 'list' | 'board') => void;
  sourceFilter: string;
  onChangeSourceFilter: (val: string) => void;
  statusFilter: string;
  onChangeStatusFilter: (val: string) => void;
  categoryFilter: string;
  onChangeCategoryFilter: (val: string) => void;
  categories: Category[];
  sortBy: string;
  sortDir: 'asc' | 'desc';
  onChangeSort: (by: string, dir: 'asc' | 'desc') => void;
  groupBy: string;
  onChangeGroupBy: (group: string) => void;
  density: 'compact' | 'comfy';
  onChangeDensity: (d: 'compact' | 'comfy') => void;
  onToggleCustomize: () => void;
}

export const Toolbar: React.FC<ToolbarProps> = ({
  viewType,
  onChangeViewType,
  sourceFilter,
  onChangeSourceFilter,
  statusFilter,
  onChangeStatusFilter,
  categoryFilter,
  onChangeCategoryFilter,
  categories,
  sortBy,
  sortDir,
  onChangeSort,
  groupBy,
  onChangeGroupBy,
  density,
  onChangeDensity,
  onToggleCustomize,
}) => {
  const [showSourceMenu, setShowSourceMenu] = useState(false);
  const [showStatusMenu, setShowStatusMenu] = useState(false);
  const [showCategoryMenu, setShowCategoryMenu] = useState(false);
  const [showSortMenu, setShowSortMenu] = useState(false);
  const [showGroupMenu, setShowGroupMenu] = useState(false);

  const toggleSortDir = () => {
    onChangeSort(sortBy, sortDir === 'asc' ? 'desc' : 'asc');
  };

  const dropdownMenuStyle: React.CSSProperties = {
    position: 'absolute',
    top: '40px',
    left: 0,
    background: '#151821',
    border: '1px solid rgba(255,255,255,0.12)',
    borderRadius: '10px',
    padding: '6px',
    zIndex: 100,
    minWidth: '150px',
    boxShadow: '0 12px 32px rgba(0,0,0,0.6)',
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
  };

  const renderDropdownItem = (label: string, onClick: () => void, isSelected: boolean) => (
    <button
      key={label}
      type="button"
      style={{
        width: '100%',
        border: 0,
        background: isSelected ? 'rgba(140, 158, 255, 0.15)' : 'transparent',
        color: isSelected ? '#8C9EFF' : '#ECEEF3',
        fontWeight: isSelected ? 600 : 400,
        textAlign: 'left',
        cursor: 'pointer',
        fontSize: '13px',
        padding: '7px 10px',
        borderRadius: '6px',
        transition: 'background 0.1s',
      }}
      onMouseEnter={(e) => {
        if (!isSelected) e.currentTarget.style.background = 'rgba(255, 255, 255, 0.06)';
      }}
      onMouseLeave={(e) => {
        if (!isSelected) e.currentTarget.style.background = 'transparent';
      }}
      onClick={onClick}
    >
      {label}
    </button>
  );

  return (
    <div className="c073" style={{ width: '100%', position: 'relative', display: 'flex', alignItems: 'center', gap: '8px' }}>
      {/* View Switcher Segmented Control */}
      <div className="c093">
        <button
          type="button"
          aria-label="Table"
          className={viewType === 'table' ? 'c094' : 'c095'}
          onClick={() => onChangeViewType('table')}
          title="Table view"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="3" y="4" width="18" height="16" rx="2"></rect>
            <path d="M3 10h18M3 15h18M9 4v16"></path>
          </svg>
        </button>

        <button
          type="button"
          aria-label="Grid"
          className={viewType === 'grid' ? 'c094' : 'c095'}
          onClick={() => onChangeViewType('grid')}
          title="Grid view (tiles)"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="3" y="3" width="7" height="7" rx="1.5"></rect>
            <rect x="14" y="3" width="7" height="7" rx="1.5"></rect>
            <rect x="3" y="14" width="7" height="7" rx="1.5"></rect>
            <rect x="14" y="14" width="7" height="7" rx="1.5"></rect>
          </svg>
        </button>

        <button
          type="button"
          aria-label="List"
          className={viewType === 'list' ? 'c094' : 'c095'}
          onClick={() => onChangeViewType('list')}
          title="List view (dense)"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <line x1="8" y1="6" x2="21" y2="6"></line>
            <line x1="8" y1="12" x2="21" y2="12"></line>
            <line x1="8" y1="18" x2="21" y2="18"></line>
            <line x1="3" y1="6" x2="3.01" y2="6"></line>
            <line x1="3" y1="12" x2="3.01" y2="12"></line>
            <line x1="3" y1="18" x2="3.01" y2="18"></line>
          </svg>
        </button>

        <button
          type="button"
          aria-label="Board"
          className={viewType === 'board' ? 'c094' : 'c095'}
          onClick={() => onChangeViewType('board')}
          title="Board view (Kanban categories)"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="3" y="3" width="5" height="18" rx="1"></rect>
            <rect x="10.5" y="3" width="5" height="12" rx="1"></rect>
            <rect x="18" y="3" width="5" height="15" rx="1"></rect>
          </svg>
        </button>
      </div>

      {/* Source Filter */}
      <div style={{ position: 'relative' }}>
        <button
          type="button"
          className="c078"
          onClick={() => setShowSourceMenu(!showSourceMenu)}
          style={{ height: '34px', padding: '0 12px', fontSize: '13px' }}
        >
          Source{sourceFilter ? `: ${sourceFilter.toUpperCase()}` : ''}
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="m6 9 6 6 6-6"></path>
          </svg>
        </button>
        {showSourceMenu && (
          <div style={dropdownMenuStyle} onMouseLeave={() => setShowSourceMenu(false)}>
            {renderDropdownItem('All sources', () => { onChangeSourceFilter(''); setShowSourceMenu(false); }, sourceFilter === '')}
            {renderDropdownItem('HOST', () => { onChangeSourceFilter('host'); setShowSourceMenu(false); }, sourceFilter === 'host')}
            {renderDropdownItem('DOCKER', () => { onChangeSourceFilter('docker'); setShowSourceMenu(false); }, sourceFilter === 'docker')}
            {renderDropdownItem('CUSTOM', () => { onChangeSourceFilter('custom'); setShowSourceMenu(false); }, sourceFilter === 'custom')}
          </div>
        )}
      </div>

      {/* Status Filter */}
      <div style={{ position: 'relative' }}>
        <button
          type="button"
          className="c078"
          onClick={() => setShowStatusMenu(!showStatusMenu)}
          style={{ height: '34px', padding: '0 12px', fontSize: '13px' }}
        >
          Status{statusFilter ? `: ${statusFilter.toUpperCase()}` : ''}
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="m6 9 6 6 6-6"></path>
          </svg>
        </button>
        {showStatusMenu && (
          <div style={dropdownMenuStyle} onMouseLeave={() => setShowStatusMenu(false)}>
            {renderDropdownItem('All status', () => { onChangeStatusFilter(''); setShowStatusMenu(false); }, statusFilter === '')}
            {renderDropdownItem('UP', () => { onChangeStatusFilter('up'); setShowStatusMenu(false); }, statusFilter === 'up')}
            {renderDropdownItem('DOWN', () => { onChangeStatusFilter('down'); setShowStatusMenu(false); }, statusFilter === 'down')}
            {renderDropdownItem('CONFLICT', () => { onChangeStatusFilter('conflict'); setShowStatusMenu(false); }, statusFilter === 'conflict')}
          </div>
        )}
      </div>

      {/* Category Filter */}
      <div style={{ position: 'relative' }}>
        <button
          type="button"
          className="c078"
          onClick={() => setShowCategoryMenu(!showCategoryMenu)}
          style={{ height: '34px', padding: '0 12px', fontSize: '13px' }}
        >
          Category{categoryFilter ? `: ${categories.find(c => c.id === categoryFilter)?.name || categoryFilter}` : ''}
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="m6 9 6 6 6-6"></path>
          </svg>
        </button>
        {showCategoryMenu && (
          <div style={{ ...dropdownMenuStyle, maxHeight: '280px', overflowY: 'auto' }} onMouseLeave={() => setShowCategoryMenu(false)}>
            {renderDropdownItem('All categories', () => { onChangeCategoryFilter(''); setShowCategoryMenu(false); }, categoryFilter === '')}
            {categories.map((c) =>
              renderDropdownItem(c.name, () => { onChangeCategoryFilter(c.id); setShowCategoryMenu(false); }, categoryFilter === c.id)
            )}
          </div>
        )}
      </div>

      {/* Sort Selector */}
      <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
        <button
          type="button"
          className="c078"
          onClick={() => setShowSortMenu(!showSortMenu)}
          style={{ height: '34px', padding: '0 12px', fontSize: '13px', borderTopRightRadius: 0, borderBottomRightRadius: 0 }}
        >
          <span style={{ textTransform: 'capitalize' }}>Sort: {sortBy}</span>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="m6 9 6 6 6-6"></path>
          </svg>
        </button>
        <button
          type="button"
          className="c078"
          onClick={toggleSortDir}
          title={`Order: ${sortDir === 'asc' ? 'Ascending' : 'Descending'}`}
          style={{ height: '34px', padding: '0 8px', fontSize: '12px', borderLeft: 0, borderTopLeftRadius: 0, borderBottomLeftRadius: 0 }}
        >
          {sortDir === 'asc' ? '↑' : '↓'}
        </button>

        {showSortMenu && (
          <div style={dropdownMenuStyle} onMouseLeave={() => setShowSortMenu(false)}>
            {[
              { id: 'port', label: 'Port number' },
              { id: 'name', label: 'App Name' },
              { id: 'cpu', label: 'CPU usage' },
              { id: 'ram', label: 'Memory RAM' },
              { id: 'uptime', label: 'Uptime' },
            ].map((s) =>
              renderDropdownItem(s.label, () => { onChangeSort(s.id, sortDir); setShowSortMenu(false); }, sortBy === s.id)
            )}
          </div>
        )}
      </div>

      {/* Grouping */}
      <div style={{ position: 'relative' }}>
        <button
          type="button"
          className="c078"
          onClick={() => setShowGroupMenu(!showGroupMenu)}
          style={{ height: '34px', padding: '0 12px', fontSize: '13px' }}
        >
          Group: {groupBy === 'none' ? 'None' : groupBy}
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="m6 9 6 6 6-6"></path>
          </svg>
        </button>

        {showGroupMenu && (
          <div style={{ ...dropdownMenuStyle, right: 0, left: 'auto' }} onMouseLeave={() => setShowGroupMenu(false)}>
            {['none', 'category', 'source', 'status'].map((g) =>
              renderDropdownItem(g === 'none' ? 'No grouping' : `Group by ${g}`, () => { onChangeGroupBy(g); setShowGroupMenu(false); }, groupBy === g)
            )}
          </div>
        )}
      </div>

      {/* Columns / Customize Trigger */}
      <button
        type="button"
        className="c077"
        aria-label="Customize layout"
        onClick={onToggleCustomize}
        title="Customize layout & card fields"
        style={{ width: '34px', height: '34px', borderRadius: '9px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="3" y="4" width="18" height="16" rx="2"></rect>
          <path d="M9 4v16M15 4v16"></path>
        </svg>
      </button>

      {/* Density Toggle */}
      <div className="c093" style={{ marginLeft: 'auto' }}>
        <button
          type="button"
          aria-label="Compact"
          className={density === 'compact' ? 'c094' : 'c095'}
          onClick={() => onChangeDensity('compact')}
        >
          Compact
        </button>
        <button
          type="button"
          aria-label="Comfy"
          className={density === 'comfy' ? 'c094' : 'c095'}
          onClick={() => onChangeDensity('comfy')}
        >
          Comfy
        </button>
      </div>
    </div>
  );
};
