import React, { useEffect, useState } from 'react';
import { api } from './api';
import { AddAppModal } from './components/AddAppModal';
import { AppDetailModal } from './components/AppDetailModal';
import { BoardView } from './components/BoardView';
import { BulkActionBar } from './components/BulkActionBar';
import { CommandPalette } from './components/CommandPalette';
import { ConflictsView } from './components/ConflictsView';
import { CustomizeDrawer } from './components/CustomizeDrawer';
import { GridView } from './components/GridView';
import { HistoryView } from './components/HistoryView';
import { KeyboardShortcutsModal } from './components/KeyboardShortcutsModal';
import { ListView } from './components/ListView';
import { OverviewView } from './components/OverviewView';
import { SavedViewTabs } from './components/SavedViewTabs';
import { Sidebar } from './components/Sidebar';
import { StatsStrip } from './components/StatsStrip';
import { SystemDrawer } from './components/SystemDrawer';
import { TableView } from './components/TableView';
import { Toolbar } from './components/Toolbar';
import { TopBar } from './components/TopBar';
import { AppItem, Category, ConflictItem, Rule, StatsData, ViewItem } from './types';

export const App: React.FC = () => {
  // Navigation & View
  const [activeNav, setActiveNav] = useState('ports');
  const [viewType, setViewType] = useState<'table' | 'grid' | 'list' | 'board'>('table');
  const [density, setDensity] = useState<'compact' | 'comfy'>('compact');
  const [theme, setTheme] = useState('dark');
  const [accent, setAccent] = useState('#8C9EFF');
  const [safeMode, setSafeMode] = useState(true);

  // Data
  const [apps, setApps] = useState<AppItem[]>([]);
  const [conflicts, setConflicts] = useState<ConflictItem[]>([]);
  const [stats, setStats] = useState<StatsData | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [views, setViews] = useState<ViewItem[]>([]);
  const [activeViewId, setActiveViewId] = useState('all');
  const [lastScanTime, setLastScanTime] = useState<number>(Date.now() / 1000);
  const [dockerAvailable, setDockerAvailable] = useState(true);
  const [dockerMsg, setDockerMsg] = useState('');
  const [dockerBannerDismissed, setDockerBannerDismissed] = useState(false);

  // Visible Columns / Card Fields
  const [visibleFields, setVisibleFields] = useState<Record<string, boolean>>({
    port: true,
    source: true,
    bind: true,
    cpuram: true,
    uptime: true,
  });

  // Filters & Search
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [sourceFilter, setSourceFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [sortBy, setSortBy] = useState('port');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [groupBy, setGroupBy] = useState('none');

  // Selection
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  // Modals & Drawers
  const [detailApp, setDetailApp] = useState<AppItem | null>(null);
  const [showAddApp, setShowAddApp] = useState(false);
  const [showCustomize, setShowCustomize] = useState(false);
  const [showSystemDrawer, setShowSystemDrawer] = useState(false);
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const [showShortcutsModal, setShowShortcutsModal] = useState(false);
  const [showNewCatModal, setShowNewCatModal] = useState(false);
  const [newCatName, setNewCatName] = useState('');
  const [newCatColor, setNewCatColor] = useState('#8C9EFF');

  // Initial Load
  useEffect(() => {
    loadInitialData();
  }, []);

  // Theme Sync
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  // Global Keyboard Shortcuts
  useEffect(() => {
    let gPressedAt = 0;

    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const isInput = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable);

      // Escape closes open overlays
      if (e.key === 'Escape') {
        setShowShortcutsModal(false);
        setShowCommandPalette(false);
        setShowAddApp(false);
        setShowCustomize(false);
        setShowSystemDrawer(false);
        setShowNewCatModal(false);
        setDetailApp(null);
        return;
      }

      if (isInput) return;

      if (e.key === '?') {
        e.preventDefault();
        setShowShortcutsModal((prev) => !prev);
        return;
      }

      if (e.key === '/') {
        e.preventDefault();
        const searchInput = document.querySelector('input[type="text"]') as HTMLInputElement;
        if (searchInput) {
          searchInput.focus();
          searchInput.select();
        }
        return;
      }

      const now = Date.now();
      if (e.key.toLowerCase() === 'g') {
        gPressedAt = now;
        return;
      }

      if (now - gPressedAt < 1000) {
        if (e.key.toLowerCase() === 't') { setViewType('table'); gPressedAt = 0; }
        else if (e.key.toLowerCase() === 'g') { setViewType('grid'); gPressedAt = 0; }
        else if (e.key.toLowerCase() === 'b') { setViewType('board'); gPressedAt = 0; }
        else if (e.key.toLowerCase() === 'l') { setViewType('list'); gPressedAt = 0; }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Real-time SSE Stream with Exponential Backoff Reconnect & Polling Fallback
  useEffect(() => {
    let es: EventSource | null = null;
    let fallbackInterval: any = null;
    let reconnectTimeout: any = null;
    let reconnectAttempts = 0;
    let isComponentMounted = true;

    const startPollingFallback = () => {
      if (!fallbackInterval && isComponentMounted) {
        fallbackInterval = setInterval(fetchAppsAndStats, 4000);
      }
    };

    const stopPollingFallback = () => {
      if (fallbackInterval) {
        clearInterval(fallbackInterval);
        fallbackInterval = null;
      }
    };

    const connectSSE = () => {
      if (!isComponentMounted) return;
      if (es) {
        try { es.close(); } catch {}
        es = null;
      }

      try {
        es = new EventSource('/api/stream');

        es.onopen = () => {
          reconnectAttempts = 0;
          stopPollingFallback();
        };

        es.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.apps) setApps(data.apps);
            if (data.conflicts) setConflicts(data.conflicts);
            if (data.stats) setStats(data.stats);
            if (data.last_scan) setLastScanTime(data.last_scan);
          } catch {}
        };

        es.onerror = () => {
          if (es) {
            try { es.close(); } catch {}
            es = null;
          }
          startPollingFallback();

          if (isComponentMounted) {
            const delay = Math.min(30000, 2000 * Math.pow(1.5, reconnectAttempts));
            reconnectAttempts++;
            if (reconnectTimeout) clearTimeout(reconnectTimeout);
            reconnectTimeout = setTimeout(() => {
              if (isComponentMounted) {
                connectSSE();
              }
            }, delay);
          }
        };
      } catch {
        startPollingFallback();
        if (isComponentMounted) {
          reconnectTimeout = setTimeout(connectSSE, 4000);
        }
      }
    };

    connectSSE();

    return () => {
      isComponentMounted = false;
      if (es) {
        try { es.close(); } catch {}
      }
      if (fallbackInterval) clearInterval(fallbackInterval);
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, []);

  const loadInitialData = async () => {
    try {
      const [appData, statData, catData, ruleData, viewData, setts] = await Promise.all([
        api.getApps(),
        api.getStats(),
        api.getCategories(),
        api.getRules(),
        api.getViews(),
        api.getSettings(),
      ]);

      setApps(appData.apps);
      setConflicts(appData.conflicts);
      setDockerAvailable(appData.docker_status.available);
      setDockerMsg(appData.docker_status.message);
      setLastScanTime(appData.last_scan);
      setStats(statData);
      setCategories(catData);
      setRules(ruleData);
      setViews(viewData);

      if (setts.safe_mode) setSafeMode(setts.safe_mode.toLowerCase() === 'true');
      if (setts.theme) setTheme(setts.theme);
      if (setts.accent) setAccent(setts.accent);
      if (setts.density) setDensity(setts.density as any);
      if (setts.default_view) setViewType(setts.default_view as any);
    } catch (e) {
      console.error('Error loading initial data:', e);
    }
  };

  const fetchAppsAndStats = async () => {
    try {
      const [appData, statData] = await Promise.all([api.getApps(), api.getStats()]);
      setApps(appData.apps);
      setConflicts(appData.conflicts);
      setStats(statData);
      setLastScanTime(appData.last_scan);
    } catch {}
  };

  // Safe Mode Toggle
  const handleToggleSafeMode = async (newVal: boolean) => {
    setSafeMode(newVal);
    await api.updateSettings({ safe_mode: String(newVal) });
  };

  // Theme Toggle
  const handleToggleTheme = () => {
    const nextTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(nextTheme);
    api.updateSettings({ theme: nextTheme });
  };

  // Scan Trigger
  const handleTriggerScan = async () => {
    await api.triggerScan();
    await fetchAppsAndStats();
  };

  // Saved View Selection
  const handleSelectView = (vId: string) => {
    setActiveViewId(vId);
    setSelectedCategory(null);
    if (vId === 'all') {
      setSourceFilter('');
      setStatusFilter('');
      setCategoryFilter('');
    } else if (vId === 'dev') {
      setSourceFilter('');
      setStatusFilter('');
      setCategoryFilter('development');
    } else if (vId === 'exposed') {
      setSourceFilter('');
      setStatusFilter('');
      setCategoryFilter('');
    } else if (vId === 'docker') {
      setSourceFilter('docker');
      setStatusFilter('');
      setCategoryFilter('');
    }
  };

  // Save Custom View
  const handleSaveCurrentView = async (name: string) => {
    const vId = `v_${Date.now()}`;
    const newView: ViewItem = {
      id: vId,
      name,
      filters: { source: sourceFilter, status: statusFilter, category: categoryFilter },
      sort: { by: sortBy, dir: sortDir },
      group_by: groupBy,
      view_type: viewType,
      columns: [],
    };
    await api.saveView(newView);
    setViews((prev) => [...prev, newView]);
    setActiveViewId(vId);
  };

  // Selection
  const handleToggleSelect = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const handleSelectAll = () => {
    if (selectedIds.length === displayedApps.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(displayedApps.map((a) => a.id));
    }
  };

  // Bulk Actions
  const handleBulkMove = async (catId: string) => {
    await api.bulkAction({ ids: selectedIds, action: 'move', category_id: catId });
    setSelectedIds([]);
    await fetchAppsAndStats();
  };

  const handleBulkAddTag = async (tag: string) => {
    await api.bulkAction({ ids: selectedIds, action: 'tag', tag });
    setSelectedIds([]);
    await fetchAppsAndStats();
  };

  const handleBulkPin = async () => {
    await api.bulkAction({ ids: selectedIds, action: 'pin' });
    setSelectedIds([]);
    await fetchAppsAndStats();
  };

  const handleBulkHide = async () => {
    await api.bulkAction({ ids: selectedIds, action: 'hide' });
    setSelectedIds([]);
    await fetchAppsAndStats();
  };

  const handleBulkStart = async () => {
    await api.bulkAction({ ids: selectedIds, action: 'start' });
    setSelectedIds([]);
    await fetchAppsAndStats();
  };

  const handleBulkStop = async () => {
    await api.bulkAction({ ids: selectedIds, action: 'stop' });
    setSelectedIds([]);
    await fetchAppsAndStats();
  };

  const handleBulkRestart = async () => {
    await api.bulkAction({ ids: selectedIds, action: 'restart' });
    setSelectedIds([]);
    await fetchAppsAndStats();
  };

  // Quick Row Actions
  const handleQuickStart = async (app: AppItem, e: React.MouseEvent) => {
    e.stopPropagation();
    if (safeMode) { alert('Safe mode is ON. Mutations are locked.'); return; }
    try {
      await api.startApp(app.id);
      await fetchAppsAndStats();
    } catch (err: any) {
      alert(`Start failed: ${err.message}`);
    }
  };

  const handleQuickStop = async (app: AppItem, e: React.MouseEvent) => {
    e.stopPropagation();
    if (safeMode) { alert('Safe mode is ON. Mutations are locked.'); return; }
    try {
      await api.stopApp(app.id);
      await fetchAppsAndStats();
    } catch (err: any) {
      alert(`Stop failed: ${err.message}`);
    }
  };

  const handleQuickLogs = (app: AppItem, e: React.MouseEvent) => {
    e.stopPropagation();
    setDetailApp(app);
  };

  // Drag and Drop move category
  const handleMoveCategory = async (appId: string, newCatId: string) => {
    await api.patchApp(appId, { category_id: newCatId });
    await fetchAppsAndStats();
  };

  // Create new category
  const handleCreateCategory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCatName.trim()) return;
    const catId = newCatName.toLowerCase().replace(/[^a-z0-9]/g, '-');
    await api.saveCategory({
      id: catId,
      name: newCatName.trim(),
      color: newCatColor,
      mode: 'manual',
      sort_order: categories.length + 1,
    });
    const updatedCats = await api.getCategories();
    setCategories(updatedCats);
    setShowNewCatModal(false);
    setNewCatName('');
  };

  // Handle navigation
  const handleSelectNav = (nav: string) => {
    if (nav === 'system') {
      setShowSystemDrawer(true);
      return;
    }
    setActiveNav(nav);
  };

  // Filter & Sort Pipeline
  let displayedApps = apps.filter((a) => !a.hidden);

  if (activeNav === 'docker') {
    displayedApps = displayedApps.filter((a) => a.source === 'docker');
  } else if (activeNav === 'conflicts') {
    displayedApps = displayedApps.filter((a) => a.status === 'conflict');
  }

  if (activeViewId === 'exposed') {
    displayedApps = displayedApps.filter((a) => a.bind === '0.0.0.0');
  }

  if (selectedCategory) {
    displayedApps = displayedApps.filter((a) => a.category_id === selectedCategory);
  }

  if (categoryFilter) {
    displayedApps = displayedApps.filter((a) => a.category_id === categoryFilter);
  }

  if (sourceFilter) {
    displayedApps = displayedApps.filter((a) => a.source.toLowerCase() === sourceFilter.toLowerCase());
  }

  if (statusFilter) {
    displayedApps = displayedApps.filter((a) => a.status.toLowerCase() === statusFilter.toLowerCase());
  }

  if (search) {
    const s = search.toLowerCase();
    displayedApps = displayedApps.filter(
      (a) =>
        a.name.toLowerCase().includes(s) ||
        String(a.port).includes(s) ||
        (a.process_name && a.process_name.toLowerCase().includes(s)) ||
        (a.image && a.image.toLowerCase().includes(s)) ||
        a.tags.some((t) => t.toLowerCase().includes(s))
    );
  }

  // Sorting
  displayedApps.sort((a, b) => {
    let diff = 0;
    if (sortBy === 'port') diff = a.port - b.port;
    else if (sortBy === 'name') diff = a.name.localeCompare(b.name);
    else if (sortBy === 'cpu') diff = (a.cpu_percent || 0) - (b.cpu_percent || 0);
    else if (sortBy === 'ram') diff = (a.ram_mb || 0) - (b.ram_mb || 0);
    else if (sortBy === 'uptime') diff = (a.uptime_sec || 0) - (b.uptime_sec || 0);
    return sortDir === 'asc' ? diff : -diff;
  });

  return (
    <div className="c042" style={{ display: 'flex', width: '100%', minHeight: '100vh', background: 'var(--bg)' }}>
      {/* Sidebar */}
      <Sidebar
        activeNav={activeNav}
        onSelectNav={handleSelectNav}
        categories={categories}
        selectedCategory={selectedCategory}
        onSelectCategory={setSelectedCategory}
        onNewCategoryClick={() => setShowNewCatModal(true)}
        conflictCount={conflicts.length}
        safeMode={safeMode}
        onToggleSafeMode={handleToggleSafeMode}
      />

      {/* Main Content Area */}
      <main className="c067" style={{ flex: '1 1 700px', minWidth: 0, padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {/* Top Bar */}
        <TopBar
          title={
            selectedCategory
              ? (categories.find(c => c.id === selectedCategory)?.name || 'Category')
              : (activeNav.charAt(0).toUpperCase() + activeNav.slice(1))
          }
          search={search}
          onSearchChange={setSearch}
          onOpenCommandPalette={() => setShowCommandPalette(true)}
          onOpenAddApp={() => setShowAddApp(true)}
          onTriggerScan={handleTriggerScan}
          theme={theme}
          onToggleTheme={handleToggleTheme}
          lastScanTime={lastScanTime}
        />

        {/* Docker unavailable banner if applicable */}
        {!dockerAvailable && !dockerBannerDismissed && (
          <div
            style={{
              padding: '12px 18px',
              borderRadius: '12px',
              background: 'rgba(251, 191, 119, 0.08)',
              border: '1px solid rgba(251, 191, 119, 0.22)',
              color: '#FBBF77',
              fontSize: '13px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '12px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div
                style={{
                  width: '28px',
                  height: '28px',
                  borderRadius: '7px',
                  background: 'rgba(251, 191, 119, 0.15)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                  <line x1="12" y1="9" x2="12" y2="13"></line>
                  <line x1="12" y1="17" x2="12.01" y2="17"></line>
                </svg>
              </div>
              <div>
                <span style={{ fontWeight: 600, color: '#ECEEF3' }}>Docker Daemon Not Running</span>
                <span style={{ color: '#8D95A5', marginLeft: '8px' }}>
                  Displaying host listening processes only. Start Docker Desktop to inspect containers and published ports.
                </span>
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
              <button
                type="button"
                className="row-action-btn"
                style={{ height: '28px', width: 'auto', padding: '0 10px', fontSize: '12px', color: '#FBBF77', borderColor: 'rgba(251, 191, 119, 0.3)' }}
                onClick={handleTriggerScan}
                title="Retry Docker socket connection"
              >
                Retry
              </button>
              <button
                type="button"
                className="row-action-btn"
                style={{ height: '28px', width: '28px' }}
                onClick={() => setDockerBannerDismissed(true)}
                title="Dismiss notice"
              >
                ✕
              </button>
            </div>
          </div>
        )}

        {/* Dedicated Views Based on Navigation */}
        {activeNav === 'overview' ? (
          <OverviewView
            apps={apps}
            categories={categories}
            conflicts={conflicts}
            stats={stats}
            onOpenDetail={setDetailApp}
            onSelectNav={handleSelectNav}
          />
        ) : activeNav === 'history' ? (
          <HistoryView />
        ) : activeNav === 'conflicts' ? (
          <ConflictsView
            conflicts={conflicts}
            apps={apps}
            onOpenDetail={setDetailApp}
            onSelectNav={handleSelectNav}
          />
        ) : (
          <>
            {/* Single-Line Stats Strip */}
            <StatsStrip
              stats={stats}
              onOpenSystemDrawer={() => setShowSystemDrawer(true)}
            />

            {/* Saved View Tabs */}
            <SavedViewTabs
              views={views}
              activeViewId={activeViewId}
              onSelectView={handleSelectView}
              onSaveCurrentView={handleSaveCurrentView}
              appsCount={apps.length}
              devCount={apps.filter((a) => a.category_id === 'development').length}
              exposedCount={apps.filter((a) => a.bind === '0.0.0.0').length}
              dockerCount={apps.filter((a) => a.source === 'docker').length}
            />

            {/* Single-Line Toolbar */}
            <Toolbar
              viewType={viewType}
              onChangeViewType={setViewType}
              sourceFilter={sourceFilter}
              onChangeSourceFilter={setSourceFilter}
              statusFilter={statusFilter}
              onChangeStatusFilter={setStatusFilter}
              categoryFilter={categoryFilter}
              onChangeCategoryFilter={setCategoryFilter}
              categories={categories}
              sortBy={sortBy}
              sortDir={sortDir}
              onChangeSort={(by, dir) => { setSortBy(by); setSortDir(dir); }}
              groupBy={groupBy}
              onChangeGroupBy={setGroupBy}
              density={density}
              onChangeDensity={setDensity}
              onToggleCustomize={() => setShowCustomize(true)}
            />

            {/* Views Container */}
            <div style={{ flex: 1, minHeight: 0 }}>
              {viewType === 'table' && (
                <TableView
                  apps={displayedApps}
                  selectedIds={selectedIds}
                  onToggleSelect={handleToggleSelect}
                  onSelectAll={handleSelectAll}
                  categories={categories}
                  density={density}
                  onOpenDetail={setDetailApp}
                  onQuickStart={handleQuickStart}
                  onQuickStop={handleQuickStop}
                  onQuickLogs={handleQuickLogs}
                  safeMode={safeMode}
                  visibleFields={visibleFields}
                  groupBy={groupBy}
                />
              )}

              {viewType === 'grid' && (
                <GridView
                  apps={displayedApps}
                  onOpenDetail={setDetailApp}
                  categories={categories}
                  visibleFields={visibleFields}
                />
              )}

              {viewType === 'list' && (
                <ListView
                  apps={displayedApps}
                  onOpenDetail={setDetailApp}
                  categories={categories}
                />
              )}

              {viewType === 'board' && (
                <BoardView
                  apps={displayedApps}
                  categories={categories}
                  onOpenDetail={setDetailApp}
                  onMoveAppCategory={handleMoveCategory}
                  onNewCategoryClick={() => setShowNewCatModal(true)}
                />
              )}
            </div>
          </>
        )}

        {/* Footer info strip */}
        <div className="c145" style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#8D95A5', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '14px', marginTop: 'auto' }}>
          <span>{displayedApps.length} of {apps.length} ports · Portly listening on port 5533</span>
          <span>SSE Live updates active · Auto-refresh 3s · Press ? for shortcuts</span>
        </div>
      </main>

      {/* Floating Bulk Action Bar */}
      <BulkActionBar
        selectedCount={selectedIds.length}
        categories={categories}
        onMoveToCategory={handleBulkMove}
        onAddTag={handleBulkAddTag}
        onPin={handleBulkPin}
        onHide={handleBulkHide}
        onStart={handleBulkStart}
        onStop={handleBulkStop}
        onRestart={handleBulkRestart}
        onClear={() => setSelectedIds([])}
      />

      {/* Detail Modal */}
      {detailApp && (
        <AppDetailModal
          app={detailApp}
          onClose={() => setDetailApp(null)}
          categories={categories}
          safeMode={safeMode}
          onRefreshApps={fetchAppsAndStats}
        />
      )}

      {/* Add Custom App Modal */}
      {showAddApp && (
        <AddAppModal
          onClose={() => setShowAddApp(false)}
          categories={categories}
          availableApps={apps}
          onAppAdded={fetchAppsAndStats}
        />
      )}

      {/* Customize Drawer */}
      {showCustomize && (
        <CustomizeDrawer
          onClose={() => setShowCustomize(false)}
          viewType={viewType}
          onChangeViewType={setViewType}
          density={density}
          onChangeDensity={setDensity}
          groupBy={groupBy}
          onChangeGroupBy={setGroupBy}
          sortBy={sortBy}
          onChangeSortBy={setSortBy}
          categories={categories}
          rules={rules}
          onRulesUpdated={async () => {
            const r = await api.getRules();
            setRules(r);
            await fetchAppsAndStats();
          }}
          accent={accent}
          onChangeAccent={(col) => {
            setAccent(col);
            document.documentElement.style.setProperty('--accent', col);
            api.updateSettings({ accent: col });
          }}
          visibleFields={visibleFields}
          onToggleField={(field) =>
            setVisibleFields((prev) => ({ ...prev, [field]: !prev[field] }))
          }
        />
      )}

      {/* System Stats Drawer */}
      {showSystemDrawer && (
        <SystemDrawer onClose={() => setShowSystemDrawer(false)} />
      )}

      {/* Command Palette */}
      <CommandPalette
        isOpen={showCommandPalette}
        onClose={() => setShowCommandPalette(false)}
        apps={apps}
        onSelectApp={setDetailApp}
        onTriggerScan={handleTriggerScan}
        onSwitchView={setViewType}
        onOpenAddApp={() => setShowAddApp(true)}
        onToggleSafeMode={() => handleToggleSafeMode(!safeMode)}
        safeMode={safeMode}
      />

      {/* Keyboard Shortcuts Modal */}
      <KeyboardShortcutsModal
        isOpen={showShortcutsModal}
        onClose={() => setShowShortcutsModal(false)}
      />

      {/* New Category Modal */}
      {showNewCatModal && (
        <div className="modal-backdrop" onClick={() => setShowNewCatModal(false)}>
          <div className="modal-content" style={{ width: '380px', background: '#151821', border: '1px solid rgba(255,255,255,0.12)', borderRadius: '14px', padding: '24px' }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 14px 0', fontSize: '16px', fontWeight: 600 }}>Create New Category</h3>
            <form onSubmit={handleCreateCategory}>
              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>Category Name</label>
                <input
                  type="text"
                  placeholder="e.g. AI Models"
                  value={newCatName}
                  onChange={(e) => setNewCatName(e.target.value)}
                  autoFocus
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                  required
                />
              </div>

              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>Color</label>
                <div style={{ display: 'flex', gap: '8px' }}>
                  {['#8C9EFF', '#5EEAD4', '#FBBF77', '#F5A3D0', '#B6E36B', '#C4B5FD', '#FF8A8A'].map((col) => (
                    <button
                      key={col}
                      type="button"
                      onClick={() => setNewCatColor(col)}
                      style={{
                        width: '26px',
                        height: '26px',
                        borderRadius: '6px',
                        backgroundColor: col,
                        border: newCatColor === col ? '2px solid #FFFFFF' : '2px solid transparent',
                        cursor: 'pointer',
                      }}
                    />
                  ))}
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button type="button" className="c078" onClick={() => setShowNewCatModal(false)}>Cancel</button>
                <button type="submit" className="c080">Create Category</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
