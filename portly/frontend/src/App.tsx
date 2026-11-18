import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Icon } from './components/Icon';
import { api, resolveAppUrl } from './api';
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
import { StacksView } from './components/StacksView';
import { StatsStrip } from './components/StatsStrip';
import { SystemDrawer } from './components/SystemDrawer';
import { TableView } from './components/TableView';
import { Toolbar } from './components/Toolbar';
import { TopBar } from './components/TopBar';
import { UserManagementDrawer } from './components/UserManagementDrawer';
import { useToast } from './components/Toast';
import { AppItem, Category, ConflictItem, Rule, StatsData, ViewItem } from './types';

interface AppProps {
  user?: any;
  onLogout?: () => void;
}

export const App: React.FC<AppProps> = ({ user, onLogout }) => {
  const readOnly = user?.role === 'viewer';
  const { success, error, warning, info } = useToast();

  // Navigation & View
  const [activeNav, setActiveNav] = useState('ports');
  const [viewType, setViewType] = useState<'table' | 'grid' | 'list' | 'board'>('table');
  const [density, setDensity] = useState<'compact' | 'comfy'>('compact');
  const [theme, setTheme] = useState<'dark' | 'light' | 'oled' | 'system'>('dark');
  const [accent, setAccent] = useState('#8C9EFF');
  const [safeMode, setSafeMode] = useState(true);
  const [unlockCountdown, setUnlockCountdown] = useState<number | null>(null);
  const [kioskMode, setKioskMode] = useState(false);
  const [kioskAutoCycle, setKioskAutoCycle] = useState(false);

  // Data
  const [apps, setApps] = useState<AppItem[]>([]);
  const [conflicts, setConflicts] = useState<ConflictItem[]>([]);
  const [stats, setStats] = useState<StatsData | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [views, setViews] = useState<ViewItem[]>([]);
  const [activeViewId, setActiveViewId] = useState('all');
  const [lastScanTime, setLastScanTime] = useState<number>(Date.now() / 1000);
  const [events, setEvents] = useState<any[]>([]);
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
  const [tagFilter, setTagFilter] = useState('');
  const [sortBy, setSortBy] = useState('port');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [groupBy, setGroupBy] = useState('none');
  const [showHidden, setShowHidden] = useState(false);

  // Selection
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  // Modals & Drawers
  const [detailAppId, setDetailAppId] = useState<string | null>(null);
  const [showAddApp, setShowAddApp] = useState(false);
  const [adoptingApp, setAdoptingApp] = useState<AppItem | null>(null);
  const [showCustomize, setShowCustomize] = useState(false);
  const [showSystemDrawer, setShowSystemDrawer] = useState(false);
  const [showUserManagement, setShowUserManagement] = useState(false);
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
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const apply = () => document.documentElement.setAttribute(
      'data-theme', theme === 'system' ? (media.matches ? 'dark' : 'light') : theme,
    );
    apply();
    media.addEventListener('change', apply);
    return () => media.removeEventListener('change', apply);
  }, [theme]);

  useEffect(() => {
    document.documentElement.style.setProperty('--accent', accent);
    document.documentElement.style.setProperty('--app-accent', accent);
  }, [accent]);

  // Safe Mode Auto-Relock Countdown Timer
  useEffect(() => {
    if (safeMode || unlockCountdown === null) return;
    if (unlockCountdown <= 0) {
      handleToggleSafeMode(true);
      info('Safe mode automatically re-locked.');
      return;
    }
    const timer = setInterval(() => {
      setUnlockCountdown((prev) => (prev !== null && prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [safeMode, unlockCountdown]);

  // Kiosk Auto-Cycle Timer (30s rotation between Overview, Ports, Conflicts)
  useEffect(() => {
    if (!kioskMode || !kioskAutoCycle) return;
    const viewsToCycle = ['overview', 'ports', 'conflicts'];
    const timer = setInterval(() => {
      setActiveNav((current) => {
        const idx = viewsToCycle.indexOf(current);
        const nextIdx = (idx + 1) % viewsToCycle.length;
        return viewsToCycle[nextIdx];
      });
    }, 30000);
    return () => clearInterval(timer);
  }, [kioskMode, kioskAutoCycle]);

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
        setShowUserManagement(false);
        setShowNewCatModal(false);
        setDetailAppId(null);
        return;
      }

      // Ctrl+K / Cmd+K works from anywhere including inside inputs (D-6)
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setShowCommandPalette((prev) => !prev);
        return;
      }

      if (isInput) return;

      if (e.shiftKey && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setKioskMode((prev) => !prev);
        return;
      }

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
            if (data.apps) setApps(data.apps.map(resolveAppUrl));
            if (data.conflicts) setConflicts(data.conflicts);
            if (data.stats) setStats(data.stats);
            if (data.docker_status) {
              setDockerAvailable(data.docker_status.available);
              setDockerMsg(data.docker_status.message || '');
            }
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
      const [appData, statData, catData, ruleData, viewData, setts, eventData] = await Promise.all([
        api.getApps({ include_hidden: true }),
        api.getStats(),
        api.getCategories(),
        api.getRules(),
        api.getViews(),
        api.getSettings(),
        api.getEvents(),
      ]);

      setApps(appData.apps);
      setConflicts(appData.conflicts);
      setEvents(eventData.slice(0, 8));
      setDockerAvailable(appData.docker_status.available);
      setDockerMsg(appData.docker_status.message);
      setLastScanTime(appData.last_scan);
      setStats(statData);
      setCategories(catData);
      setRules(ruleData);
      setViews(viewData);

      if (setts.safe_mode) setSafeMode(setts.safe_mode.toLowerCase() === 'true');
      if (setts.theme) setTheme(setts.theme as any);
      if (setts.accent) setAccent(setts.accent);
      if (setts.density) setDensity(setts.density as any);
      if (setts.default_view) setViewType(setts.default_view as any);
    } catch (e) {
      console.error('Error loading initial data:', e);
    }
  };

  const fetchAppsAndStats = async () => {
    try {
      const [appData, statData] = await Promise.all([api.getApps({ include_hidden: true }), api.getStats()]);
      setApps(appData.apps);
      setConflicts(appData.conflicts);
      setStats(statData);
      setLastScanTime(appData.last_scan);
    } catch {}
  };

  // Safe Mode Toggle with Auto-Relock & Rollback Error Handling (P1-17, D-8, F-10)
  const handleToggleSafeMode = async (newVal: boolean, autoRelockSec?: number) => {
    const prev = safeMode;
    const prevCountdown = unlockCountdown;
    setSafeMode(newVal);
    if (!newVal && autoRelockSec) {
      setUnlockCountdown(autoRelockSec);
    } else {
      setUnlockCountdown(null);
    }

    try {
      await api.updateSettings({ safe_mode: String(newVal) });
      if (!newVal) {
        warning(
          autoRelockSec
            ? `Safe mode disabled for ${Math.floor(autoRelockSec / 60)} minutes.`
            : 'Safe mode disabled indefinitely. Live actions unlocked.'
        );
      } else {
        success('Safe mode enabled. Real mutations are locked.');
      }
    } catch (err: any) {
      setSafeMode(prev);
      setUnlockCountdown(prevCountdown);
      error(`Failed to update safe mode: ${err.message || 'Network error'}`);
    }
  };

  // Theme Toggle — serialize writes so rapid clicks land in order
  const settingsQueue = useRef<Promise<unknown>>(Promise.resolve());
  const persistSetting = (patch: Record<string, string>) => {
    settingsQueue.current = settingsQueue.current
      .catch(() => {})
      .then(() => api.updateSettings(patch));
  };

  const handleToggleTheme = () => {
    const nextTheme = theme === 'dark' ? 'light' : theme === 'light' ? 'oled' : theme === 'oled' ? 'system' : 'dark';
    setTheme(nextTheme);
    persistSetting({ theme: nextTheme });
  };

  const handleSetTheme = (t: 'dark' | 'light' | 'oled' | 'system') => {
    setTheme(t);
    persistSetting({ theme: t });
  };

  const handleSetDensity = (d: 'compact' | 'comfy') => {
    setDensity(d);
    persistSetting({ density: d });
  };

  // Scan Trigger
  const handleTriggerScan = async () => {
    if (readOnly) {
      warning('Viewer access is read-only.');
      return;
    }
    await api.triggerScan();
    await fetchAppsAndStats();
  };

  // Saved View Selection (P1-15: loads saved filters, sort, grouping, view_type)
  const handleSelectView = (vId: string) => {
    setActiveViewId(vId);
    setSelectedCategory(null);

    const custom = views.find((v) => v.id === vId);
    if (custom) {
      if (custom.filters) {
        setSourceFilter(custom.filters.source || '');
        setStatusFilter(custom.filters.status || '');
        setCategoryFilter(custom.filters.category || '');
      }
      if (custom.sort) {
        setSortBy(custom.sort.by || 'port');
        setSortDir((custom.sort.dir as any) || 'asc');
      }
      if (custom.group_by) {
        setGroupBy(custom.group_by);
      }
      if (custom.view_type) {
        setViewType(custom.view_type as any);
      }
      return;
    }

    // Default views fallback
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
    if (readOnly) {
      warning('Viewer access is read-only.');
      return;
    }
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
    if (displayedIds.length > 0 && selectedDisplayedIds.length === displayedIds.length) {
      setSelectedIds((prev) => prev.filter((id) => !displayedIds.includes(id)));
    } else {
      setSelectedIds((prev) => [...new Set([...prev, ...displayedIds])]);
    }
  };

  // Bulk Actions
  const runBulk = async (action: string, extra: { category_id?: string; tag?: string } = {}) => {
    if (readOnly) {
      warning('Viewer access is read-only.');
      return;
    }
    if (safeMode && ['start', 'stop', 'restart'].includes(action)) {
      warning(`Safe mode is ON. Mutations are locked. Disable safe mode to ${action} apps.`);
      return;
    }
    try {
      const res = await api.bulkAction({ ids: selectedIds, action, ...extra });
      if (res.failed?.length) {
        warning(`${res.failed.length} of ${selectedIds.length} apps failed: ${res.failed.map((f) => f.id).join(', ')}`);
      } else if (res.count) {
        success(`${res.count} app${res.count === 1 ? '' : 's'} updated`);
      }
    } catch (e: any) {
      error(`Bulk ${action} failed: ${e.message}`);
    }
    setSelectedIds([]);
    await fetchAppsAndStats();
  };

  const handleBulkMove = (catId: string) => runBulk('move', { category_id: catId });
  const handleBulkAddTag = (tag: string) => runBulk('tag', { tag });
  const handleBulkPin = () => runBulk('pin');
  const handleBulkHide = () => runBulk('hide');
  const handleBulkUnhide = () => runBulk('unhide');
  const handleBulkStart = () => runBulk('start');
  const handleBulkStop = () => runBulk('stop');
  const handleBulkRestart = () => runBulk('restart');

  // Quick Row Actions
  const handleQuickStart = async (app: AppItem, e: React.MouseEvent) => {
    e.stopPropagation();
    if (readOnly || safeMode) {
      warning(readOnly ? 'Viewer access is read-only.' : 'Safe mode is ON. Mutations are locked. Disable safe mode to start apps.');
      return;
    }
    try {
      await api.startApp(app.id);
      success(`Started ${app.name}`);
      await fetchAppsAndStats();
    } catch (err: any) {
      error(`Start failed: ${err.message}`);
    }
  };

  const handleQuickStop = async (app: AppItem, e: React.MouseEvent) => {
    e.stopPropagation();
    if (readOnly || safeMode) {
      warning(readOnly ? 'Viewer access is read-only.' : 'Safe mode is ON. Mutations are locked. Disable safe mode to stop apps.');
      return;
    }
    try {
      await api.stopApp(app.id);
      success(`Stopped ${app.name}`);
      await fetchAppsAndStats();
    } catch (err: any) {
      error(`Stop failed: ${err.message}`);
    }
  };

  const handleQuickLogs = (app: AppItem, e: React.MouseEvent) => {
    e.stopPropagation();
    setDetailAppId(app.id);
  };

  const handleAdoptApp = (app: AppItem) => {
    setAdoptingApp(app);
    setShowAddApp(true);
  };

  // Drag and Drop move category
  const handleMoveCategory = async (appId: string, newCatId: string) => {
    if (readOnly) {
      warning('Viewer access is read-only.');
      return;
    }
    await api.patchApp(appId, { category_id: newCatId });
    await fetchAppsAndStats();
  };

  // Create new category
  const handleCreateCategory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (readOnly) {
      warning('Viewer access is read-only.');
      return;
    }
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

  // Sidebar/view counts ignore hidden ports; the table can include them on demand.
  const visibleApps = useMemo(() => apps.filter((a) => !a.hidden), [apps]);
  const hiddenCount = apps.length - visibleApps.length;
  const allTags = useMemo(() => [...new Set(visibleApps.flatMap((a) => a.tags || []))].sort(), [visibleApps]);

  // Filter & Sort Pipeline (D-4, P1-20: Pinned apps stay on top in all views)
  const displayedApps = useMemo(() => {
    let list = showHidden ? apps : visibleApps;

    if (activeNav === 'docker') {
      list = list.filter((a) => a.source === 'docker');
    } else if (activeNav === 'conflicts') {
      list = list.filter((a) => a.status === 'conflict');
    }

    if (activeViewId === 'exposed') {
      list = list.filter((a) => a.bind === '0.0.0.0');
    } else if (activeViewId === 'dev') {
      list = list.filter((a) => a.category_id === 'development');
    } else if (activeViewId === 'docker') {
      list = list.filter((a) => a.source === 'docker');
    }

    if (selectedCategory) {
      list = list.filter((a) => a.category_id === selectedCategory);
    }

    if (categoryFilter) {
      list = list.filter((a) => a.category_id === categoryFilter);
    }

    if (sourceFilter) {
      list = list.filter((a) => a.source.toLowerCase() === sourceFilter.toLowerCase());
    }

    if (statusFilter) {
      list = list.filter((a) => a.status.toLowerCase() === statusFilter.toLowerCase());
    }

    if (tagFilter) {
      list = list.filter((a) => (a.tags || []).includes(tagFilter));
    }

    if (search) {
      const s = search.toLowerCase();
      list = list.filter(
        (a) =>
          a.name.toLowerCase().includes(s) ||
          String(a.port).includes(s) ||
          (a.process_name && a.process_name.toLowerCase().includes(s)) ||
          (a.image && a.image.toLowerCase().includes(s)) ||
          a.tags.some((t) => t.toLowerCase().includes(s))
      );
    }

    const compare = (a: AppItem, b: AppItem) => {
      let diff = 0;
      if (sortBy === 'port') diff = a.port - b.port;
      else if (sortBy === 'name') diff = a.name.localeCompare(b.name);
      else if (sortBy === 'cpu') diff = (a.cpu_percent || 0) - (b.cpu_percent || 0);
      else if (sortBy === 'ram') diff = (a.ram_mb || 0) - (b.ram_mb || 0);
      else if (sortBy === 'uptime') diff = (a.uptime_sec || 0) - (b.uptime_sec || 0);
      else if (sortBy === 'status') diff = a.status.localeCompare(b.status);
      else if (sortBy === 'category') diff = (categories.find((c) => c.id === a.category_id)?.name || '').localeCompare(categories.find((c) => c.id === b.category_id)?.name || '');
      else if (sortBy === 'order') diff = (a.sort_order || 0) - (b.sort_order || 0);
      return sortDir === 'asc' ? diff : -diff;
    };

    const pinned = list.filter((a) => a.pinned).sort(compare);
    const unpinned = list.filter((a) => !a.pinned).sort(compare);
    return [...pinned, ...unpinned];
  }, [
    apps,
    visibleApps,
    showHidden,
    activeNav,
    activeViewId,
    selectedCategory,
    categories,
    categoryFilter,
    tagFilter,
    sourceFilter,
    statusFilter,
    search,
    sortBy,
    sortDir,
  ]);

  // Bind the detail modal to live app data so SSE/refresh updates reach it.
  const detailApp = useMemo(() => apps.find((a) => a.id === detailAppId) || null, [apps, detailAppId]);

  const displayedIds = useMemo(() => displayedApps.map((a) => a.id), [displayedApps]);
  const selectedDisplayedIds = useMemo(
    () => selectedIds.filter((id) => displayedIds.includes(id)),
    [selectedIds, displayedIds],
  );

  // Prune ids whose app vanished from the stream or the current filtered view.
  useEffect(() => {
    setSelectedIds((prev) => {
      const next = prev.filter((id) => displayedIds.includes(id));
      return next.length === prev.length ? prev : next;
    });
  }, [displayedIds]);

  return (
    <div className="c042" style={{ display: 'flex', width: '100%', minHeight: '100vh', background: 'var(--bg)' }}>
      {/* Sidebar - hidden in kiosk mode */}
      {!kioskMode && (
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
          unlockCountdown={unlockCountdown}
        />
      )}

      {/* Main Content Area */}
      <main className="c067" style={{ flex: '1 1 700px', minWidth: 0, padding: kioskMode ? '16px 24px' : '24px 32px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
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
          kioskMode={kioskMode}
          onToggleKiosk={() => setKioskMode((prev) => !prev)}
          user={user}
          onOpenUserManagement={() => setShowUserManagement(true)}
          onLogout={onLogout}
          readOnly={readOnly}
        />

        {/* Safe Mode Warning Banner when safe mode is off (D-7, D-8, F-10) */}
        {!safeMode && (
          <div
            style={{
              padding: '10px 18px',
              borderRadius: '12px',
              background: 'rgba(255, 138, 138, 0.1)',
              border: '1px solid rgba(255, 138, 138, 0.3)',
              color: '#FF8A8A',
              fontSize: '13px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '12px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FBBF77" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
              <div>
                <strong>Safe Mode Unlocked:</strong> Real mutations on host processes &amp; containers are enabled.
                {unlockCountdown != null && (
                  <span style={{ marginLeft: 8, color: '#ECEEF3' }}>
                    Auto-relocking in <strong>{Math.floor(unlockCountdown / 60)}m {unlockCountdown % 60}s</strong>
                  </span>
                )}
              </div>
            </div>
            <button
              type="button"
              className="row-action-btn"
              onClick={() => handleToggleSafeMode(true)}
              style={{
                height: '28px',
                width: 'auto',
                padding: '0 12px',
                fontSize: '12px',
                fontWeight: 600,
                color: '#FF8A8A',
                borderColor: 'rgba(255, 138, 138, 0.4)',
              }}
            >
              Lock Safe Mode Now
            </button>
          </div>
        )}

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
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
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
                <Icon name="x" size={13} />
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
            events={events}
            onOpenDetail={(app) => setDetailAppId(app.id)}
            onSelectNav={handleSelectNav}
          />
        ) : activeNav === 'stacks' ? (
          <StacksView safeMode={safeMode} />
        ) : activeNav === 'history' ? (
          <HistoryView />
        ) : activeNav === 'conflicts' ? (
          <ConflictsView
            conflicts={conflicts}
            apps={apps}
            onOpenDetail={(app) => setDetailAppId(app.id)}
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
              appsCount={visibleApps.length}
              devCount={visibleApps.filter((a) => a.category_id === 'development').length}
              exposedCount={visibleApps.filter((a) => a.bind === '0.0.0.0').length}
              dockerCount={visibleApps.filter((a) => a.source === 'docker').length}
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
              tagFilter={tagFilter}
              onChangeTagFilter={setTagFilter}
              tags={allTags}
              categories={categories}
              sortBy={sortBy}
              sortDir={sortDir}
              onChangeSort={(by, dir) => { setSortBy(by); setSortDir(dir); }}
              groupBy={groupBy}
              onChangeGroupBy={setGroupBy}
              showHidden={showHidden}
              onToggleShowHidden={() => setShowHidden((prev) => !prev)}
              hiddenCount={hiddenCount}
              density={density}
              onChangeDensity={handleSetDensity}
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
                  onOpenDetail={(app) => setDetailAppId(app.id)}
                  onQuickStart={handleQuickStart}
                  onQuickStop={handleQuickStop}
                  onQuickLogs={handleQuickLogs}
                  onAdoptApp={handleAdoptApp}
                  safeMode={safeMode}
                  readOnly={readOnly}
                  visibleFields={visibleFields}
                  groupBy={groupBy}
                />
              )}

              {viewType === 'grid' && (
                <GridView
                  apps={displayedApps}
                  onOpenDetail={(app) => setDetailAppId(app.id)}
                  categories={categories}
                  visibleFields={visibleFields}
                  onAdoptApp={handleAdoptApp}
                />
              )}

              {viewType === 'list' && (
                <ListView
                  apps={displayedApps}
                  onOpenDetail={(app) => setDetailAppId(app.id)}
                  categories={categories}
                />
              )}

              {viewType === 'board' && (
                <BoardView
                  apps={displayedApps}
                  categories={categories}
                  onOpenDetail={(app) => setDetailAppId(app.id)}
                  onMoveAppCategory={handleMoveCategory}
                  onNewCategoryClick={() => setShowNewCatModal(true)}
                  readOnly={readOnly}
                />
              )}
            </div>
          </>
        )}

        {/* Footer info strip */}
        <div className="c145" style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#8D95A5', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '14px', marginTop: 'auto' }}>
          <span>{displayedApps.length} of {visibleApps.length} ports · Portly listening on port {window.location.port || (window.location.protocol === 'https:' ? '443' : '80')}</span>
          <span>SSE live · 4s polling fallback · Press ? for shortcuts</span>
        </div>
      </main>

      {/* Floating Bulk Action Bar */}
      {!readOnly && <BulkActionBar
        selectedCount={selectedIds.length}
        categories={categories}
        onMoveToCategory={handleBulkMove}
        onAddTag={handleBulkAddTag}
        onPin={handleBulkPin}
        onHide={handleBulkHide}
        onUnhide={handleBulkUnhide}
        onStart={handleBulkStart}
        onStop={handleBulkStop}
        onRestart={handleBulkRestart}
        onClear={() => setSelectedIds([])}
      />}

      {/* Detail Modal */}
      {detailApp && (
        <AppDetailModal
          app={detailApp}
          onClose={() => setDetailAppId(null)}
          categories={categories}
          safeMode={safeMode}
          readOnly={readOnly}
          onRefreshApps={fetchAppsAndStats}
        />
      )}

      {/* Add Custom App Modal */}
      {showAddApp && (
        <AddAppModal
          onClose={() => {
            setShowAddApp(false);
            setAdoptingApp(null);
          }}
          categories={categories}
          availableApps={apps}
          onAppAdded={fetchAppsAndStats}
          initialAdoptApp={adoptingApp}
        />
      )}

      {/* Customize Drawer */}
      {showCustomize && (
        <CustomizeDrawer
          onClose={() => setShowCustomize(false)}
          viewType={viewType}
          onChangeViewType={setViewType}
          theme={theme}
          onChangeTheme={handleSetTheme}
          density={density}
          onChangeDensity={handleSetDensity}
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
            document.documentElement.style.setProperty('--app-accent', col);
            persistSetting({ accent: col });
          }}
          visibleFields={visibleFields}
          onToggleField={(field) =>
            setVisibleFields((prev) => ({ ...prev, [field]: !prev[field] }))
          }
          readOnly={readOnly}
        />
      )}

      {/* System Stats Drawer */}
      {showSystemDrawer && (
        <SystemDrawer onClose={() => setShowSystemDrawer(false)} />
      )}

      {/* User Management & Audit Logs Drawer */}
      <UserManagementDrawer
        isOpen={showUserManagement}
        onClose={() => setShowUserManagement(false)}
        currentUser={user}
      />

      {/* Command Palette */}
      <CommandPalette
        isOpen={showCommandPalette}
        onClose={() => setShowCommandPalette(false)}
        apps={apps}
        onSelectApp={(app) => setDetailAppId(app.id)}
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
                <label htmlFor="new-cat-name" style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>Category Name</label>
                <input
                  id="new-cat-name"
                  name="newCatName"
                  type="text"
                  placeholder="e.g. AI Models"
                  value={newCatName}
                  onChange={(e) => setNewCatName(e.target.value)}
                  autoComplete="off"
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
                      aria-label={`Select color ${col}`}
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

      {/* Floating Kiosk Controls */}
      {kioskMode && (
        <div
          style={{
            position: 'fixed',
            bottom: '24px',
            right: '24px',
            zIndex: 9999,
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
          }}
        >
          <button
            type="button"
            onClick={() => setKioskAutoCycle((prev) => !prev)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              background: kioskAutoCycle ? 'rgba(94, 234, 212, 0.2)' : 'rgba(16, 18, 24, 0.92)',
              backdropFilter: 'blur(10px)',
              border: `1px solid ${kioskAutoCycle ? '#5EEAD4' : 'rgba(255, 255, 255, 0.15)'}`,
              color: kioskAutoCycle ? '#5EEAD4' : '#ECEEF3',
              padding: '8px 14px',
              borderRadius: '24px',
              fontSize: '12px',
              fontWeight: 500,
              cursor: 'pointer',
              boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
            }}
            title="Toggle 30s automatic view cycle (Overview → Ports → Conflicts)"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 2v6h-6"></path><path d="M3 12a9 9 0 0 1 15-6.7L21 8"></path><path d="M3 22v-6h6"></path><path d="M21 12a9 9 0 0 1-15 6.7L3 16"></path></svg>
            {kioskAutoCycle ? 'Auto-Cycle ON (30s)' : 'Auto-Cycle (30s)'}
          </button>
          <button
            type="button"
            onClick={() => {
              setKioskMode(false);
              setKioskAutoCycle(false);
            }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              background: 'rgba(16, 18, 24, 0.92)',
              backdropFilter: 'blur(10px)',
              border: '1px solid rgba(140, 158, 255, 0.4)',
              color: '#ECEEF3',
              padding: '8px 16px',
              borderRadius: '24px',
              fontSize: '12px',
              fontWeight: 500,
              cursor: 'pointer',
              boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
            }}
            title="Exit Kiosk Mode (Shift + K)"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <polyline points="4 14 10 14 10 20"></polyline>
              <polyline points="20 10 14 10 14 4"></polyline>
              <line x1="14" y1="10" x2="21" y2="3"></line>
              <line x1="3" y1="21" x2="10" y2="14"></line>
            </svg>
            Exit Kiosk (Shift+K)
          </button>
        </div>
      )}
    </div>
  );
};
