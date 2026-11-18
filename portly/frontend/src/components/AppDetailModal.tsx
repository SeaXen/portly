import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { parseAnsiToReact } from '../utils/ansi';
import { useFocusTrap } from '../hooks/useFocusTrap';
import {
  AppItem,
  Category,
  CommandExecResponse,
  ComposeInfo,
  ProxyConfigResponse,
  TlsCertInfo,
} from '../types';
import { ConfirmDialog } from './ConfirmDialog';

interface AppDetailModalProps {
  app: AppItem;
  onClose: () => void;
  categories: Category[];
  safeMode: boolean;
  readOnly?: boolean;
  onRefreshApps: () => void;
}

type DetailTab =
  | 'logs'
  | 'ports'
  | 'tunnels'
  | 'proxy'
  | 'tls'
  | 'terminal'
  | 'compose'
  | 'env'
  | 'volumes'
  | 'health'
  | 'settings';

export const AppDetailModal: React.FC<AppDetailModalProps> = ({
  app,
  onClose,
  categories,
  safeMode,
  readOnly = false,
  onRefreshApps,
}) => {
  const [activeTab, setActiveTab] = useState<DetailTab>('logs');
  const [logs, setLogs] = useState<string[]>([]);
  const [logFilter, setLogFilter] = useState('');
  const [isRegexFilter, setIsRegexFilter] = useState(false);
  const [regexError, setRegexError] = useState<string | null>(null);
  const [logLevel, setLogLevel] = useState<'all' | 'info' | 'warn' | 'error'>('all');
  const [wrapLogs, setWrapLogs] = useState(false);
  const [autoFollow, setAutoFollow] = useState(true);
  const [scrollPaused, setScrollPaused] = useState(false);
  const logContainerRef = useRef<HTMLDivElement>(null);

  // Port change state
  const [targetPort, setTargetPort] = useState<number>(app.port || 3000);
  const [targetBind, setTargetBind] = useState<string>(app.bind || '0.0.0.0');
  const [portAvail, setPortAvail] = useState<{ free: boolean; used_by: string } | null>(null);
  const [portChecking, setPortChecking] = useState(false);
  const [portChanging, setPortChanging] = useState(false);

  // Reverse Proxy Generator state
  const [proxyDomain, setProxyDomain] = useState(`${app.name.toLowerCase().replace(/[^a-z0-9_-]/g, '-')}.local`);
  const [proxyFormat, setProxyFormat] = useState<'caddy' | 'nginx' | 'traefik_yaml' | 'traefik_labels' | 'cloudflared'>('caddy');
  const [proxyData, setProxyData] = useState<ProxyConfigResponse | null>(null);
  const [loadingProxy, setLoadingProxy] = useState(false);

  // Cloudflare Tunnel & Remote URL state
  const [tunnelUrl, setTunnelUrl] = useState(app.url_override || '');
  const [savingTunnel, setSavingTunnel] = useState(false);

  // Multi-Port Remapping state
  const [multiPorts, setMultiPorts] = useState<Array<{ container_port: string; host_port: number; bind: string }>>([]);
  const [multiPortsChanging, setMultiPortsChanging] = useState(false);

  // Compose Stack Action state
  const [executingStackAction, setExecutingStackAction] = useState<string | null>(null);

  // SSL/TLS state
  const [tlsData, setTlsData] = useState<TlsCertInfo | null>(null);
  const [loadingTls, setLoadingTls] = useState(false);

  // Terminal / Exec state
  const [execCmd, setExecCmd] = useState('ps aux');
  const [execRes, setExecRes] = useState<CommandExecResponse | null>(null);
  const [executing, setExecuting] = useState(false);

  // Compose state
  const [composeData, setComposeData] = useState<ComposeInfo | null>(null);
  const [loadingCompose, setLoadingCompose] = useState(false);

  // Image update state
  const [updateInfo, setUpdateInfo] = useState<any>(null);
  const [checkingUpdate, setCheckingUpdate] = useState(false);
  const [applyingUpdate, setApplyingUpdate] = useState(false);

  // Health state
  const [healthHistory, setHealthHistory] = useState<Array<{ ts: number; ok: boolean; latency_ms: number }>>([]);
  const [inspectData, setInspectData] = useState<any>(null);

  // Settings edit state
  const [customName, setCustomName] = useState(app.name);
  const [customCategory, setCustomCategory] = useState(app.category_id);
  const [tagsStr, setTagsStr] = useState(app.tags.join(', '));
  const [urlOverride, setUrlOverride] = useState(app.open_url || '');

  // Modals & Confirmation dialogs (D-1, D-2, D-11)
  const [showRollbackConfirm, setShowRollbackConfirm] = useState(false);
  const [showComposeDownConfirm, setShowComposeDownConfirm] = useState(false);
  const [showRevealEnvConfirm, setShowRevealEnvConfirm] = useState(false);
  const [revealedEnv, setRevealedEnv] = useState<string[] | null>(null);
  const [revealingEnv, setRevealingEnv] = useState(false);

  // In-modal Toast Notifications
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' | 'warning' } | null>(null);

  const showNotification = (message: string, type: 'success' | 'error' | 'info' | 'warning' = 'info') => {
    setToast({ message, type });
    setTimeout(() => {
      setToast((prev) => (prev?.message === message ? null : prev));
    }, 4500);
  };

  // Load initial details
  useEffect(() => {
    loadLogs();
    checkPortStatus(targetPort, targetBind);
    api.getAppDetail(app.id).then((d) => {
      setHealthHistory(d.health_history || []);
      setInspectData(d.docker_inspect || null);
      if (d.docker_inspect?.ports) {
        const pList: Array<{ container_port: string; host_port: number; bind: string }> = [];
        Object.entries(d.docker_inspect.ports).forEach(([cp, maps]: [string, any]) => {
          const hp = maps && maps.length > 0 ? parseInt(maps[0].HostPort) || 0 : 0;
          const b = maps && maps.length > 0 ? maps[0].HostIp || '0.0.0.0' : '0.0.0.0';
          pList.push({ container_port: cp, host_port: hp, bind: b });
        });
        if (pList.length > 0) {
          setMultiPorts(pList);
        }
      } else if (app.port) {
        setMultiPorts([{ container_port: `${app.port}/${app.proto || 'tcp'}`, host_port: app.port, bind: app.bind || '0.0.0.0' }]);
      }
    }).catch(() => {
      if (app.port) {
        setMultiPorts([{ container_port: `${app.port}/${app.proto || 'tcp'}`, host_port: app.port, bind: app.bind || '0.0.0.0' }]);
      }
    });
  }, [app.id]);

  // Live Auto-follow interval for logs
  useEffect(() => {
    if (!autoFollow || activeTab !== 'logs') return;
    const interval = setInterval(() => {
      loadLogs();
    }, 2500);
    return () => clearInterval(interval);
  }, [autoFollow, activeTab, app.id]);

  // Auto-scroll logs when new logs come in if autoFollow is checked
  useEffect(() => {
    if (autoFollow && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs, autoFollow]);

  const handleLogScroll = () => {
    if (!logContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = logContainerRef.current;
    const isNearBottom = scrollHeight - scrollTop - clientHeight <= 45;
    if (!isNearBottom && autoFollow) {
      setAutoFollow(false);
      setScrollPaused(true);
    } else if (isNearBottom && scrollPaused) {
      setScrollPaused(false);
    }
  };

  useEffect(() => {
    if (isRegexFilter && logFilter) {
      try {
        new RegExp(logFilter, 'i');
        setRegexError(null);
      } catch (e: any) {
        setRegexError(e.message || 'Invalid regular expression');
      }
    } else {
      setRegexError(null);
    }
  }, [isRegexFilter, logFilter]);

  const loadLogs = async () => {
    try {
      const res = await api.getAppLogs(app.id, 500);
      setLogs(res.lines || []);
    } catch {
      setLogs(['Failed to fetch logs.']);
    }
  };

  const checkPortStatus = async (p: number, b: string) => {
    setPortChecking(true);
    try {
      const res = await api.checkPort(p, b);
      setPortAvail(res);
    } catch {
      setPortAvail({ free: false, used_by: 'Error checking port' });
    } finally {
      setPortChecking(false);
    }
  };

  const handleSuggestPort = async () => {
    try {
      const res = await api.suggestPorts(app.port + 1, 1, targetBind);
      if (res.suggested.length > 0) {
        setTargetPort(res.suggested[0]);
        checkPortStatus(res.suggested[0], targetBind);
      }
    } catch {}
  };

  const handleApplyPortChange = async () => {
    if (safeMode) {
      showNotification('Safe mode is ON. Unlock safe mode to execute port changes.', 'warning');
      return;
    }
    setPortChanging(true);
    try {
      await api.applyPortChange(app.id, targetPort, targetBind);
      showNotification(`Port change successfully applied! App running on :${targetPort}`, 'success');
      onRefreshApps();
      setTimeout(() => onClose(), 1200);
    } catch (e: any) {
      showNotification(`Port change failed: ${e.message}`, 'error');
    } finally {
      setPortChanging(false);
    }
  };

  const handleRollback = () => {
    if (safeMode) {
      showNotification('Safe mode is ON. Unlock safe mode to execute rollback.', 'warning');
      return;
    }
    setShowRollbackConfirm(true);
  };

  const confirmRollback = async () => {
    setShowRollbackConfirm(false);
    try {
      await api.rollbackPortChange(app.id);
      showNotification('Port mapping rolled back successfully!', 'success');
      onRefreshApps();
      setTimeout(() => onClose(), 1200);
    } catch (err: any) {
      showNotification(`Rollback failed: ${err.message}`, 'error');
    }
  };

  const handleSaveTunnelUrl = async () => {
    setSavingTunnel(true);
    try {
      await api.patchApp(app.id, { url_override: tunnelUrl.trim() || undefined });
      showNotification('Cloudflare / Remote URL updated successfully!', 'success');
      onRefreshApps();
    } catch (e: any) {
      showNotification(`Failed to save URL: ${e.message}`, 'error');
    } finally {
      setSavingTunnel(false);
    }
  };

  const handleApplyMultiPorts = async () => {
    if (safeMode) {
      showNotification('Safe mode is ON. Unlock safe mode to execute port changes.', 'warning');
      return;
    }
    setMultiPortsChanging(true);
    try {
      await api.applyMultiPortChange(app.id, multiPorts.map(p => ({
        container_port: p.container_port,
        host_port: p.host_port,
        bind: p.bind || '0.0.0.0'
      })));
      showNotification('All port mappings applied successfully!', 'success');
      onRefreshApps();
      setTimeout(() => onClose(), 1200);
    } catch (e: any) {
      showNotification(`Multi-port change failed: ${e.message}`, 'error');
    } finally {
      setMultiPortsChanging(false);
    }
  };

  const handleStackAction = async (action: 'restart' | 'stop' | 'start' | 'down') => {
    if (safeMode) {
      showNotification('Safe mode is ON. Unlock safe mode to execute compose stack actions.', 'warning');
      return;
    }
    const project = composeData?.project || app.compose_project;
    if (!project) return;
    if (action === 'down') {
      setShowComposeDownConfirm(true);
      return;
    }
    executeStackActionNow(action);
  };

  const executeStackActionNow = async (action: 'restart' | 'stop' | 'start' | 'down') => {
    const project = composeData?.project || app.compose_project;
    if (!project) return;
    setExecutingStackAction(action);
    try {
      const res = await api.executeComposeAction(project, action);
      showNotification(`Stack '${project}' ${action} executed successfully (${res.affected_containers.length} containers)!`, 'success');
      onRefreshApps();
    } catch (e: any) {
      showNotification(`Stack action failed: ${e.message}`, 'error');
    } finally {
      setExecutingStackAction(null);
    }
  };

  const handleRevealEnv = async () => {
    setShowRevealEnvConfirm(false);
    setRevealingEnv(true);
    try {
      const res = await api.revealEnv(app.id);
      const envArray = Object.entries(res.env || {}).map(([k, v]) => `${k}=${v}`);
      setRevealedEnv(envArray);
      showNotification('Environment variables revealed.', 'success');
    } catch (e: any) {
      showNotification(`Failed to reveal environment variables: ${e.message}`, 'error');
    } finally {
      setRevealingEnv(false);
    }
  };

  const loadProxyConfig = async (domain?: string) => {
    if (!app.port) return;
    setLoadingProxy(true);
    try {
      const data = await api.getProxyConfig(app.id, undefined, domain || proxyDomain);
      setProxyData(data);
    } catch (e: any) {
      showNotification(`Failed to generate proxy config: ${e.message}`, 'error');
    } finally {
      setLoadingProxy(false);
    }
  };

  const loadTlsInfo = async () => {
    if (!app.port) return;
    setLoadingTls(true);
    try {
      const data = await api.getAppTls(app.id);
      setTlsData(data);
    } catch (e: any) {
      showNotification(`TLS check failed: ${e.message}`, 'error');
    } finally {
      setLoadingTls(false);
    }
  };

  const loadComposeInfo = async () => {
    if (app.source !== 'docker') return;
    setLoadingCompose(true);
    try {
      const data = await api.getAppCompose(app.id);
      setComposeData(data);
    } catch (e: any) {
      showNotification(`Compose inspection failed: ${e.message}`, 'error');
    } finally {
      setLoadingCompose(false);
    }
  };

  const handleRunExec = async (cmdToRun?: string) => {
    const cmd = cmdToRun || execCmd;
    if (!cmd.trim()) return;
    setExecuting(true);
    try {
      const res = await api.execContainerCommand(app.id, cmd);
      setExecRes(res);
      if (res.exit_code === 0) {
        showNotification(`Executed in ${res.duration_ms}ms`, 'success');
      } else {
        showNotification(`Command exited with code ${res.exit_code}`, 'warning');
      }
    } catch (e: any) {
      showNotification(`Execution failed: ${e.message}`, 'error');
    } finally {
      setExecuting(false);
    }
  };

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    showNotification(`Copied ${label} to clipboard!`, 'success');
  };

  useEffect(() => {
    if (activeTab === 'proxy' && !proxyData) {
      loadProxyConfig();
    } else if (activeTab === 'tls' && !tlsData) {
      loadTlsInfo();
    } else if (activeTab === 'compose' && !composeData) {
      loadComposeInfo();
    }
  }, [activeTab]);

  const handleCheckUpdate = async () => {
    setCheckingUpdate(true);
    try {
      const res = await api.checkImageUpdate(app.id);
      setUpdateInfo(res);
    } catch (e: any) {
      showNotification(`Update check failed: ${e.message}`, 'error');
    } finally {
      setCheckingUpdate(false);
    }
  };

  const handleApplyUpdate = async () => {
    if (safeMode) {
      showNotification('Safe mode is ON. Unlock safe mode to pull a new image.', 'warning');
      return;
    }
    setApplyingUpdate(true);
    try {
      await api.applyImageUpdate(app.id);
      showNotification('Image updated successfully!', 'success');
      setUpdateInfo(null);
      onRefreshApps();
    } catch (e: any) {
      showNotification(`Image update failed: ${e.message}`, 'error');
    } finally {
      setApplyingUpdate(false);
    }
  };

  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const tags = tagsStr.split(',').map((t) => t.trim()).filter(Boolean);
      await api.patchApp(app.id, {
        name: customName,
        category_id: customCategory,
        tags,
        url_override: urlOverride || undefined,
      });
      showNotification('Settings updated successfully!', 'success');
      onRefreshApps();
    } catch (e: any) {
      showNotification(`Failed to save settings: ${e.message}`, 'error');
    }
  };

  // Filter logs by search & level
  const filteredLogs = logs.filter((l) => {
    if (logFilter) {
      if (isRegexFilter) {
        try {
          const re = new RegExp(logFilter, 'i');
          if (!re.test(l)) return false;
        } catch {
          return false;
        }
      } else {
        if (!l.toLowerCase().includes(logFilter.toLowerCase())) {
          return false;
        }
      }
    }
    if (logLevel === 'all') return true;
    const lower = l.toLowerCase();
    if (logLevel === 'info') return lower.includes('info');
    if (logLevel === 'warn') return lower.includes('warn');
    if (logLevel === 'error') return lower.includes('error') || lower.includes('err') || lower.includes('fail');
    return true;
  });

  const initial = (app.name || 'A').charAt(0).toUpperCase();
  const containerRef = useFocusTrap<HTMLDivElement>(true, onClose);

  return (
    <div className="modal-backdrop" onClick={onClose} style={{ zIndex: 1100 }}>
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="app-detail-title"
        className="modal-content"
        style={{
          width: '1180px',
          maxWidth: '96vw',
          maxHeight: '92vh',
          background: '#0E1116',
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: '16px',
          padding: '24px',
          boxSizing: 'border-box',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '18px',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="c068" style={{ borderBottom: '1px solid rgba(255,255,255,0.07)', paddingBottom: '16px' }}>
          <div className="c187" style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <div
              className="c188"
              aria-hidden="true"
              style={{
                width: '42px',
                height: '42px',
                borderRadius: '12px',
                background: app.source === 'docker' ? 'rgba(94, 234, 212, 0.15)' : 'rgba(140, 158, 255, 0.15)',
                color: app.source === 'docker' ? '#5EEAD4' : '#8C9EFF',
                fontWeight: 700,
                fontSize: '18px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              {initial}
            </div>
            <div>
              <div className="c189" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <h1 id="app-detail-title" className="c070" style={{ margin: 0, fontSize: '20px' }}>{app.name}</h1>
                <span className={app.source === 'docker' ? 'c111' : 'c109'} style={{ textTransform: 'capitalize' }}>
                  {app.source}
                </span>
                <span className="c121" style={{ fontSize: '12px' }}>
                  <span
                    className="c122"
                    style={{
                      backgroundColor: app.status === 'up' ? '#5EEAD4' : (app.status === 'down' ? '#FF8A8A' : '#FBBF77'),
                    }}
                  />
                  <span style={{ textTransform: 'capitalize' }}>{app.status}</span>
                </span>
              </div>
              <div className="c190" style={{ fontSize: '13px', color: '#8D95A5', marginTop: '4px' }}>
                <span className="c191" style={{ fontFamily: 'JetBrains Mono, monospace', color: '#ECEEF3' }}>
                  {app.source === 'docker' ? app.image : (app.process_name || 'Host Process')}
                </span>
                {' · '}
                <span style={{ fontFamily: 'JetBrains Mono, monospace', color: '#8C9EFF', fontWeight: 600 }}>
                  :{app.port}
                </span>
                {' · '}
                <span>{app.bind}</span>
              </div>
            </div>
          </div>

          {/* Header Action Buttons */}
          <div className="c192" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {app.open_url && (
              <a href={app.open_url} target="_blank" rel="noreferrer" className="c078" style={{ textDecoration: 'none' }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"></path>
                </svg>
                Open ↗
              </a>
            )}

            <button
              type="button"
              className="c078"
              disabled={readOnly}
              title={readOnly ? 'Viewer access is read-only' : undefined}
              onClick={async () => {
                if (safeMode) {
                  showNotification('Safe mode is ON. Unlock safe mode in the sidebar to control apps.', 'warning');
                  return;
                }
                try {
                  await api.startApp(app.id);
                  showNotification(`Started ${app.name}`, 'success');
                  onRefreshApps();
                } catch (e: any) {
                  showNotification(`Failed to start: ${e.message}`, 'error');
                }
              }}
            >
              Start
            </button>

            <button
              type="button"
              className="c078"
              disabled={readOnly}
              title={readOnly ? 'Viewer access is read-only' : undefined}
              onClick={async () => {
                if (safeMode) {
                  showNotification('Safe mode is ON. Unlock safe mode in the sidebar to control apps.', 'warning');
                  return;
                }
                try {
                  await api.stopApp(app.id);
                  showNotification(`Stopped ${app.name}`, 'info');
                  onRefreshApps();
                } catch (e: any) {
                  showNotification(`Failed to stop: ${e.message}`, 'error');
                }
              }}
            >
              Stop
            </button>

            {(app as any).update_cmd && app.id.startsWith('custom:') && (
              <button
                type="button"
                className="c078"
                disabled={readOnly}
                title={readOnly ? 'Viewer access is read-only' : undefined}
                onClick={async () => {
                  if (safeMode) {
                    showNotification('Safe mode is ON. Unlock safe mode in the sidebar to control apps.', 'warning');
                    return;
                  }
                  try {
                    const res = await api.updateCustomApp(app.id);
                    showNotification(res.status === 'ok' ? 'Update command completed' : `Update failed: ${res.stderr || res.stdout || 'unknown error'}`, res.status === 'ok' ? 'success' : 'error');
                  } catch (e: any) {
                    showNotification(`Update failed: ${e.message}`, 'error');
                  }
                }}
              >
                Update
              </button>
            )}

            <button
              type="button"
              className="c078"
              disabled={readOnly}
              title={readOnly ? 'Viewer access is read-only' : undefined}
              onClick={async () => {
                if (safeMode) {
                  showNotification('Safe mode is ON. Unlock safe mode in the sidebar to control apps.', 'warning');
                  return;
                }
                try {
                  await api.restartApp(app.id);
                  showNotification(`Restarted ${app.name}`, 'success');
                  onRefreshApps();
                } catch (e: any) {
                  showNotification(`Failed to restart: ${e.message}`, 'error');
                }
              }}
            >
              Restart
            </button>

            <button type="button" className="c077" onClick={onClose} aria-label="Close dialog">
              ✕
            </button>
          </div>
        </div>

        {/* In-modal Notification Toast Banner */}
        {toast && (
          <div
            style={{
              padding: '10px 16px',
              margin: '0 24px 16px',
              borderRadius: '8px',
              fontSize: '13px',
              fontWeight: 500,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '12px',
              background:
                toast.type === 'success' ? 'rgba(94, 234, 212, 0.15)' :
                toast.type === 'error' ? 'rgba(255, 92, 92, 0.18)' :
                toast.type === 'warning' ? 'rgba(251, 191, 119, 0.18)' :
                'rgba(140, 158, 255, 0.18)',
              color:
                toast.type === 'success' ? '#5EEAD4' :
                toast.type === 'error' ? '#FF8A8A' :
                toast.type === 'warning' ? '#FBBF77' :
                '#8C9EFF',
              border: `1px solid ${
                toast.type === 'success' ? 'rgba(94, 234, 212, 0.3)' :
                toast.type === 'error' ? 'rgba(255, 92, 92, 0.3)' :
                toast.type === 'warning' ? 'rgba(251, 191, 119, 0.3)' :
                'rgba(140, 158, 255, 0.3)'
              }`,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontWeight: 700, fontSize: '13px' }}>{toast.type === 'success' ? '✓' : toast.type === 'error' ? '✕' : toast.type === 'warning' ? '!' : 'i'}</span>
              <span>{toast.message}</span>
            </div>
            <button
              type="button"
              onClick={() => setToast(null)}
              style={{
                background: 'none',
                border: 'none',
                color: 'inherit',
                cursor: 'pointer',
                fontSize: '14px',
                padding: '0 4px',
                opacity: 0.8,
              }}
            >
              ✕
            </button>
          </div>
        )}

        {/* App stats strip */}
        <div className="c081">
          <div className="c082">
            <div className="c083">
              <div className="c084">CPU</div>
              <div className="c085">{app.cpu_percent || 0}%</div>
              <div className="c086">Process load</div>
            </div>
            <svg width="40" height="22" viewBox="0 0 60 22" preserveAspectRatio="none" className="c087">
              <polyline points="0.0,20.0 20.0,12.0 40.0,16.0 60.0,8.0" fill="none" stroke="#8C9EFF" strokeWidth="1.6" />
            </svg>
          </div>

          <div className="c088">
            <div className="c083">
              <div className="c084">Memory</div>
              <div className="c085">{app.ram_mb || 0} MB</div>
              <div className="c086">RSS allocated</div>
            </div>
            <svg width="40" height="22" viewBox="0 0 60 22" preserveAspectRatio="none" className="c087">
              <polyline points="0.0,20.0 20.0,20.0 40.0,15.0 60.0,15.0" fill="none" stroke="#8C9EFF" strokeWidth="1.6" />
            </svg>
          </div>

          <div className="c088">
            <div className="c083">
              <div className="c084">Protocol</div>
              <div className="c085" style={{ textTransform: 'uppercase' }}>{app.proto}</div>
              <div className="c086">{app.bind}</div>
            </div>
          </div>

          <div className="c088">
            <div className="c083">
              <div className="c084">Uptime</div>
              <div className="c085">
                {app.uptime_sec > 3600
                  ? `${Math.floor(app.uptime_sec / 3600)}h ${Math.floor((app.uptime_sec % 3600) / 60)}m`
                  : `${Math.floor(app.uptime_sec / 60)}m`}
              </div>
              <div className="c086">Active running</div>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="c089" style={{ borderBottom: '1px solid rgba(255,255,255,0.07)', display: 'flex', overflowX: 'auto', gap: '4px' }}>
          {([
            'logs',
            'ports',
            'tunnels',
            'proxy',
            'tls',
            ...(app.source === 'docker' ? (['terminal', 'compose'] as const) : []),
            'env',
            'volumes',
            'health',
            'settings',
          ] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              className={activeTab === tab ? 'c195' : 'c196'}
              onClick={() => setActiveTab(tab as DetailTab)}
              style={{
                background: 'transparent',
                border: 'none',
                borderBottom: activeTab === tab ? '2px solid #8C9EFF' : '2px solid transparent',
                cursor: 'pointer',
                font: 'inherit',
                fontSize: '13.5px',
                padding: '10px 14px',
                textTransform: 'capitalize',
                whiteSpace: 'nowrap',
                color: activeTab === tab ? '#ECEEF3' : '#8D95A5',
              }}
            >
              {tab === 'tls' ? 'TLS / SSL' : tab === 'proxy' ? 'Reverse Proxy' : tab === 'tunnels' ? 'Cloudflare / Tunnels' : tab}
            </button>
          ))}
        </div>

        {/* Tab Contents + Right Side Cards */}
        <div className="c147" style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '20px' }}>
          {/* Main Column */}
          <div className="c194" style={{ minWidth: 0 }}>
            {activeTab === 'logs' && (
              <div>
                {/* Log Toolbar */}
                <div className="c073" style={{ marginBottom: '12px', flexWrap: 'wrap', gap: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <label className="c197" style={{ display: 'flex', alignItems: 'center', gap: '8px', background: '#151821', padding: '0 10px', borderRadius: '8px', border: `1px solid ${regexError ? '#FF8A8A' : 'rgba(255,255,255,0.08)'}` }}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <circle cx="11" cy="11" r="7"></circle>
                        <path d="m20 20-3.5-3.5"></path>
                      </svg>
                      <input
                        type="text"
                        name="logFilter"
                        aria-label="Filter logs"
                        autoComplete="off"
                        placeholder={isRegexFilter ? "Regex pattern…" : "Filter logs…"}
                        value={logFilter}
                        onChange={(e) => setLogFilter(e.target.value)}
                        className="c198"
                        style={{ background: 'transparent', border: 0, outline: 0, color: '#ECEEF3', fontSize: '13px', width: '150px', height: '32px' }}
                      />
                    </label>
                    <button
                      type="button"
                      title={isRegexFilter ? "Regular Expression ON (click to disable)" : "Toggle Regular Expression"}
                      onClick={() => setIsRegexFilter(!isRegexFilter)}
                      style={{
                        background: isRegexFilter ? 'rgba(140, 158, 255, 0.25)' : '#151821',
                        color: isRegexFilter ? '#8C9EFF' : '#8D95A5',
                        border: `1px solid ${isRegexFilter ? '#8C9EFF' : 'rgba(255,255,255,0.08)'}`,
                        borderRadius: '8px',
                        fontSize: '12px',
                        fontFamily: 'monospace',
                        fontWeight: 700,
                        padding: '0 8px',
                        height: '32px',
                        cursor: 'pointer',
                      }}
                    >
                      .*
                    </button>
                  </div>

                  <div className="c093">
                    {(['all', 'info', 'warn', 'error'] as const).map((lvl) => (
                      <button
                        key={lvl}
                        type="button"
                        className={logLevel === lvl ? 'c094' : 'c095'}
                        onClick={() => setLogLevel(lvl)}
                        style={{ textTransform: 'capitalize' }}
                      >
                        {lvl}
                      </button>
                    ))}
                  </div>

                  <span style={{ flex: 1 }} />

                  <label className="c199" style={{ fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px', color: '#8D95A5', cursor: 'pointer' }}>
                    Follow
                    <input
                      type="checkbox"
                      role="switch"
                      checked={autoFollow}
                      onChange={(e) => {
                        setAutoFollow(e.target.checked);
                        if (e.target.checked) setScrollPaused(false);
                      }}
                      className="c173"
                    />
                  </label>

                  <button
                    type="button"
                    className="c078"
                    onClick={() => setWrapLogs(!wrapLogs)}
                    style={{ background: wrapLogs ? '#1C2030' : '#151821' }}
                  >
                    Wrap
                  </button>

                  <button
                    type="button"
                    className="c078"
                    title="Copy full logs buffer to clipboard"
                    onClick={() => copyToClipboard(logs.join('\n'), 'all logs')}
                  >
                    Copy All
                  </button>

                  <button
                    type="button"
                    className="c077"
                    aria-label="Download logs"
                    title="Download logs"
                    onClick={() => {
                      const blob = new Blob([logs.join('\n')], { type: 'text/plain' });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = `${app.name.toLowerCase().replace(/\s+/g, '-')}-logs.txt`;
                      a.click();
                      URL.revokeObjectURL(url);
                    }}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <path d="M12 4v11M7 11l5 5 5-5M4 20h16"></path>
                    </svg>
                  </button>

                  <button
                    type="button"
                    className="c077"
                    aria-label="Clear view"
                    title="Clear current view"
                    onClick={() => setLogs([])}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"></path>
                    </svg>
                  </button>
                </div>

                {regexError && (
                  <div style={{ color: '#FF8A8A', fontSize: '11px', marginBottom: '8px', paddingLeft: '4px' }}>
                    ⚠ Regex error: {regexError}
                  </div>
                )}

                {/* Log Terminal Window */}
                <div style={{ position: 'relative' }}>
                  <div
                    ref={logContainerRef}
                    onScroll={handleLogScroll}
                    className="c200"
                    style={{
                      background: '#080A0E',
                      border: '1px solid rgba(255,255,255,0.07)',
                      borderRadius: '12px',
                      padding: '16px',
                      fontFamily: 'JetBrains Mono, monospace',
                      fontSize: '12px',
                      lineHeight: 1.6,
                      height: '420px',
                      overflowY: 'auto',
                      whiteSpace: wrapLogs ? 'pre-wrap' : 'pre',
                    }}
                  >
                    {filteredLogs.length === 0 ? (
                      <div style={{ color: '#8D95A5', textAlign: 'center', paddingTop: '40px' }}>
                        No logs matching current filter.
                      </div>
                    ) : (
                      filteredLogs.map((line, idx) => {
                        const hasAnsi = /(?:\x1b|\u001b)\[/.test(line);
                        const lower = line.toLowerCase();
                        const isErr = lower.includes('error') || lower.includes('fail');
                        const isWarn = lower.includes('warn');
                        const defaultColor = isErr ? '#FF8A8A' : (isWarn ? '#FBBF77' : '#ECEEF3');

                        return (
                          <div key={idx} className="c201" style={{ color: defaultColor }}>
                            {hasAnsi ? parseAnsiToReact(line) : line}
                          </div>
                        );
                      })
                    )}
                  </div>

                  {scrollPaused && (
                    <button
                      type="button"
                      onClick={() => {
                        setAutoFollow(true);
                        setScrollPaused(false);
                        if (logContainerRef.current) {
                          logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
                        }
                      }}
                      style={{
                        position: 'absolute',
                        bottom: '16px',
                        left: '50%',
                        transform: 'translateX(-50%)',
                        background: '#1A1E2C',
                        color: '#8C9EFF',
                        border: '1px solid rgba(140, 158, 255, 0.4)',
                        borderRadius: '20px',
                        padding: '6px 16px',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: 'pointer',
                        boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        zIndex: 10,
                      }}
                    >
                      <span>Auto-scroll paused ⏸</span>
                      <span style={{ textDecoration: 'underline', color: '#ECEEF3' }}>Resume</span>
                    </button>
                  )}
                </div>
              </div>
            )}

            {activeTab === 'ports' && (
              <div style={{ background: '#101218', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '12px', padding: '20px' }}>
                <h3 style={{ margin: '0 0 16px 0', fontSize: '16px', fontWeight: 600 }}>Port Mapping Editor</h3>
                <p style={{ fontSize: '13px', color: '#8D95A5', lineHeight: 1.5, marginBottom: '20px' }}>
                  Change the host port this service binds to. For Docker containers, this safely inspects, recreates the container, and verifies health with automatic rollback support.
                </p>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                  <div>
                    <label htmlFor="edit-host-port" style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>New Host Port</label>
                    <input
                      id="edit-host-port"
                      name="targetPort"
                      type="number"
                      value={targetPort}
                      onChange={(e) => {
                        const p = parseInt(e.target.value) || 0;
                        setTargetPort(p);
                        checkPortStatus(p, targetBind);
                      }}
                      className="c218"
                      style={{ width: '100%', boxSizing: 'border-box' }}
                    />
                  </div>

                  <div>
                    <label htmlFor="edit-bind-addr" style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>Bind Address</label>
                    <select
                      id="edit-bind-addr"
                      name="targetBind"
                      value={targetBind}
                      onChange={(e) => {
                        setTargetBind(e.target.value);
                        checkPortStatus(targetPort, e.target.value);
                      }}
                      className="c215"
                      style={{ width: '100%', boxSizing: 'border-box' }}
                    >
                      <option value="0.0.0.0">0.0.0.0 (All interfaces / LAN)</option>
                      <option value="127.0.0.1">127.0.0.1 (This machine only)</option>
                    </select>
                  </div>
                </div>

                {/* Availability status */}
                {portAvail && (
                  <div
                    aria-live="polite"
                    style={{
                      padding: '12px 14px',
                      borderRadius: '8px',
                      background: portAvail.free ? 'rgba(94, 234, 212, 0.1)' : 'rgba(255, 138, 138, 0.1)',
                      border: `1px solid ${portAvail.free ? 'rgba(94, 234, 212, 0.25)' : 'rgba(255, 138, 138, 0.25)'}`,
                      color: portAvail.free ? '#5EEAD4' : '#FF8A8A',
                      fontSize: '13px',
                      marginBottom: '20px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                    }}
                  >
                    <span>{portAvail.free ? '✓' : '✗'}</span>
                    <span>{portAvail.free ? `Port ${targetPort} is available and free to bind.` : `Port ${targetPort} conflict: ${portAvail.used_by}`}</span>
                  </div>
                )}

                <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                  <button type="button" className="c078" onClick={handleSuggestPort}>
                    Suggest free port
                  </button>
                  <button
                    type="button"
                    className="c080"
                    disabled={portChanging || !portAvail?.free}
                    onClick={handleApplyPortChange}
                  >
                    {portChanging ? 'Recreating…' : 'Apply and recreate'}
                  </button>
                  {app.source === 'docker' && (
                    <button
                      type="button"
                      className="c078"
                      style={{ color: '#FF8A8A', borderColor: 'rgba(255,138,138,0.3)', marginLeft: 'auto' }}
                      onClick={handleRollback}
                    >
                      Rollback Snapshot
                    </button>
                  )}
                </div>

                {app.source === 'docker' && multiPorts.length > 0 && (
                  <div style={{ marginTop: '24px', paddingTop: '20px', borderTop: '1px solid rgba(255,255,255,0.07)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                      <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 600, color: '#ECEEF3' }}>
                        All Container Ports ({multiPorts.length} Exposed)
                      </h4>
                      <span style={{ fontSize: '11px', color: '#8D95A5' }}>Remap multiple ports in one operation</span>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '16px' }}>
                      {multiPorts.map((mp, idx) => (
                        <div key={idx} style={{ display: 'grid', gridTemplateColumns: '120px 1fr 140px', gap: '12px', alignItems: 'center', background: '#090B10', padding: '10px 14px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
                          <div>
                            <span style={{ fontSize: '11px', color: '#8D95A5', display: 'block' }}>Container Port</span>
                            <code style={{ color: '#5EEAD4', fontFamily: 'JetBrains Mono, monospace', fontSize: '13px' }}>{mp.container_port}</code>
                          </div>
                          <div>
                            <label htmlFor={`edit-multi-host-port-${idx}`} style={{ display: 'block', fontSize: '11px', color: '#8D95A5' }}>Host Port</label>
                            <input
                              id={`edit-multi-host-port-${idx}`}
                              type="number"
                              value={mp.host_port}
                              onChange={(e) => {
                                const newHp = parseInt(e.target.value) || 0;
                                setMultiPorts(prev => prev.map((p, i) => i === idx ? { ...p, host_port: newHp } : p));
                              }}
                              className="c218"
                              style={{ width: '100%', height: '32px', boxSizing: 'border-box' }}
                            />
                          </div>
                          <div>
                            <label htmlFor={`edit-multi-bind-ip-${idx}`} style={{ display: 'block', fontSize: '11px', color: '#8D95A5' }}>Bind</label>
                            <select
                              id={`edit-multi-bind-ip-${idx}`}
                              value={mp.bind}
                              onChange={(e) => {
                                const newB = e.target.value;
                                setMultiPorts(prev => prev.map((p, i) => i === idx ? { ...p, bind: newB } : p));
                              }}
                              className="c215"
                              style={{ width: '100%', height: '32px', boxSizing: 'border-box' }}
                            >
                              <option value="0.0.0.0">0.0.0.0</option>
                              <option value="127.0.0.1">127.0.0.1</option>
                            </select>
                          </div>
                        </div>
                      ))}
                    </div>

                    <button
                      type="button"
                      className="c080"
                      disabled={multiPortsChanging}
                      onClick={handleApplyMultiPorts}
                    >
                      {multiPortsChanging ? 'Recreating Container…' : 'Apply Multi-Port Changes'}
                    </button>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'tunnels' && (
              <div style={{ background: '#101218', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '12px', padding: '20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                  <div>
                    <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span>Cloudflare Tunnel & Remote Access</span>
                      <span style={{ fontSize: '11px', background: 'rgba(251, 191, 119, 0.15)', color: '#FBBF77', padding: '2px 8px', borderRadius: '6px' }}>
                        Zero Trust
                      </span>
                    </h3>
                    <p style={{ margin: '6px 0 0 0', fontSize: '13px', color: '#8D95A5' }}>
                      Assign a manual Cloudflare Tunnel URL, Tailscale Funnel, or custom domain to access this service securely from anywhere.
                    </p>
                  </div>
                </div>

                <div style={{ marginBottom: '18px' }}>
                  <label htmlFor="tunnel-url-input" style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>
                    Public URL / Cloudflare Tunnel URL
                  </label>
                  <div style={{ display: 'flex', gap: '10px' }}>
                    <input
                      id="tunnel-url-input"
                      type="url"
                      placeholder="e.g. https://grafana.mydomain.com or https://name.trycloudflare.com"
                      value={tunnelUrl}
                      onChange={(e) => setTunnelUrl(e.target.value)}
                      className="c220"
                      style={{ flex: 1 }}
                    />
                    <button
                      type="button"
                      className="c080"
                      disabled={savingTunnel}
                      onClick={handleSaveTunnelUrl}
                    >
                      {savingTunnel ? 'Saving…' : 'Save URL'}
                    </button>
                    {tunnelUrl && (
                      <a
                        href={tunnelUrl.startsWith('http') ? tunnelUrl : `https://${tunnelUrl}`}
                        target="_blank"
                        rel="noreferrer"
                        className="c078"
                        style={{ display: 'flex', alignItems: 'center', gap: '4px', textDecoration: 'none' }}
                      >
                        Open ↗
                      </a>
                    )}
                  </div>
                </div>

                <div style={{ background: '#090B10', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '8px', padding: '16px', fontSize: '12.5px', color: '#8D95A5', lineHeight: 1.6 }}>
                  <strong style={{ color: '#ECEEF3', display: 'block', marginBottom: '6px' }}>⚡ How to configure Cloudflare Tunnel:</strong>
                  <ol style={{ margin: '0 0 0 18px', padding: 0 }}>
                    <li>Run Cloudflare Tunnel on your host or in Docker (<code>cloudflared tunnel run &lt;tunnel-name&gt;</code>).</li>
                    <li>In the <strong>Reverse Proxy</strong> tab above, select <strong>Cloudflare Tunnel</strong> to get your exact copy-paste <code>ingress:</code> rule.</li>
                    <li>Enter your assigned public tunnel domain above and click <strong>Save URL</strong>. Portly will display direct remote access links on your dashboard.</li>
                  </ol>
                </div>
              </div>
            )}

            {activeTab === 'proxy' && (
              <div style={{ background: '#101218', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '12px', padding: '20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                  <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>1-Click Reverse Proxy Generator</h3>
                  <div style={{ display: 'flex', gap: '6px' }}>
                    {(['caddy', 'nginx', 'traefik_yaml', 'traefik_labels', 'cloudflared'] as const).map((fmt) => (
                      <button
                        key={fmt}
                        type="button"
                        className={proxyFormat === fmt ? 'c080' : 'c078'}
                        style={{ height: '28px', padding: '0 10px', fontSize: '12px', textTransform: 'capitalize' }}
                        onClick={() => setProxyFormat(fmt)}
                      >
                        {fmt === 'traefik_yaml' ? 'Traefik YAML' : fmt === 'traefik_labels' ? 'Traefik Labels' : fmt === 'cloudflared' ? 'Cloudflare Tunnel' : fmt.toUpperCase()}
                      </button>
                    ))}
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '10px', marginBottom: '16px' }}>
                  <input
                    type="text"
                    name="proxyDomain"
                    aria-label="Proxy domain"
                    autoComplete="off"
                    value={proxyDomain}
                    onChange={(e) => setProxyDomain(e.target.value)}
                    placeholder="e.g. app.example.com"
                    className="c220"
                    style={{ flex: 1 }}
                  />
                  <button
                    type="button"
                    className="c078"
                    disabled={loadingProxy}
                    onClick={() => loadProxyConfig(proxyDomain)}
                  >
                    {loadingProxy ? 'Generating…' : 'Regenerate'}
                  </button>
                </div>

                {proxyData && (
                  <div>
                    <div style={{ position: 'relative' }}>
                      <pre
                        style={{
                          background: '#090B10',
                          border: '1px solid rgba(255,255,255,0.08)',
                          borderRadius: '8px',
                          padding: '16px',
                          fontSize: '12.5px',
                          fontFamily: 'JetBrains Mono, monospace',
                          color: '#ECEEF3',
                          overflowX: 'auto',
                          margin: 0,
                          lineHeight: 1.5,
                        }}
                      >
                        {proxyData.configs[proxyFormat]}
                      </pre>
                      <button
                        type="button"
                        className="c078"
                        style={{ position: 'absolute', top: '10px', right: '10px', height: '28px', fontSize: '12px' }}
                        onClick={() => copyToClipboard(proxyData.configs[proxyFormat] || '', proxyFormat.toUpperCase())}
                      >
                        Copy Snippet
                      </button>
                    </div>
                    <div style={{ fontSize: '12px', color: '#8D95A5', marginTop: '10px', display: 'flex', justifyContent: 'space-between' }}>
                      <span>Target: <code>{proxyData.upstream_host}:{proxyData.port}</code></span>
                      <span>Domain: <code>{proxyData.domain}</code></span>
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'tls' && (
              <div style={{ background: '#101218', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '12px', padding: '20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                  <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>SSL / TLS Certificate Inspector</h3>
                  <button
                    type="button"
                    className="c078"
                    disabled={loadingTls}
                    onClick={loadTlsInfo}
                  >
                    {loadingTls ? 'Checking…' : 'Re-check Certificate'}
                  </button>
                </div>

                {loadingTls ? (
                  <p style={{ color: '#8D95A5', fontSize: '13px' }}>Probing TLS handshake on :{app.port}…</p>
                ) : tlsData?.is_tls ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                      <div style={{ padding: '14px', background: '#151821', borderRadius: '8px' }}>
                        <div style={{ fontSize: '11px', color: '#8D95A5', textTransform: 'uppercase' }}>Certificate Status</div>
                        <div style={{ fontSize: '18px', fontWeight: 700, color: tlsData.expired ? '#FF8A8A' : '#5EEAD4', marginTop: '4px' }}>
                          {tlsData.expired ? 'EXPIRED' : 'VALID & ACTIVE'}
                        </div>
                      </div>
                      <div style={{ padding: '14px', background: '#151821', borderRadius: '8px' }}>
                        <div style={{ fontSize: '11px', color: '#8D95A5', textTransform: 'uppercase' }}>Days Remaining</div>
                        <div
                          style={{
                            fontSize: '18px',
                            fontWeight: 700,
                            color: (tlsData.days_remaining ?? 0) < 14 ? '#FF8A8A' : ((tlsData.days_remaining ?? 0) < 30 ? '#FBBF77' : '#5EEAD4'),
                            marginTop: '4px',
                          }}
                        >
                          {tlsData.days_remaining !== null && tlsData.days_remaining !== undefined ? `${tlsData.days_remaining} days` : 'N/A'}
                        </div>
                      </div>
                    </div>

                    <div style={{ fontSize: '13px', background: '#151821', borderRadius: '8px', padding: '14px', lineHeight: 1.6 }}>
                      <div><strong style={{ color: '#8D95A5' }}>Issuer:</strong> <span style={{ color: '#ECEEF3' }}>{tlsData.issuer || 'Unknown'}</span></div>
                      <div><strong style={{ color: '#8D95A5' }}>Subject:</strong> <span style={{ color: '#ECEEF3' }}>{tlsData.subject || 'Unknown'}</span></div>
                      <div><strong style={{ color: '#8D95A5' }}>Valid From:</strong> <span style={{ color: '#ECEEF3' }}>{tlsData.valid_from || 'N/A'}</span></div>
                      <div><strong style={{ color: '#8D95A5' }}>Valid Until:</strong> <span style={{ color: '#ECEEF3' }}>{tlsData.valid_until || 'N/A'}</span></div>
                      {tlsData.self_signed && <div style={{ color: '#FBBF77', marginTop: '6px' }}>⚠️ Self-signed certificate</div>}
                    </div>

                    {tlsData.san && tlsData.san.length > 0 && (
                      <div>
                        <div style={{ fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>Subject Alternative Names (SAN)</div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                          {tlsData.san.map((s, idx) => (
                            <span key={idx} style={{ fontSize: '11px', padding: '2px 8px', background: 'rgba(140, 158, 255, 0.15)', color: '#8C9EFF', borderRadius: '4px', fontFamily: 'JetBrains Mono, monospace' }}>
                              {s}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div style={{ padding: '24px', textAlign: 'center', background: '#151821', borderRadius: '8px', color: '#8D95A5', fontSize: '13px' }}>
                    <div style={{ fontSize: '24px', marginBottom: '8px' }}>ℹ</div>
                    Port {app.port} is not responding over TLS/HTTPS (standard HTTP or TCP socket).
                    <div style={{ marginTop: '8px', fontSize: '12px', color: '#8C9EFF' }}>
                      Tip: Use the Reverse Proxy tab to put Caddy or Nginx in front of this service to add automatic HTTPS.
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'terminal' && app.source === 'docker' && (
              <div style={{ background: '#101218', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '12px', padding: '20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
                  <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>Container Command Runner (`docker exec`)</h3>
                  {safeMode && (
                    <span style={{ fontSize: '11px', background: 'rgba(94, 234, 212, 0.12)', color: '#5EEAD4', padding: '3px 8px', borderRadius: '6px' }}>
                      Safe Mode: Read-only diagnostics active
                    </span>
                  )}
                </div>

                <div style={{ display: 'flex', gap: '6px', marginBottom: '12px', flexWrap: 'wrap' }}>
                  {['ps aux', 'df -h', 'env', 'netstat -tuln', 'uname -a', 'cat /etc/hosts'].map((preset) => (
                    <button
                      key={preset}
                      type="button"
                      className="c078"
                      style={{ height: '26px', fontSize: '11px', padding: '0 8px', fontFamily: 'JetBrains Mono, monospace' }}
                      onClick={() => {
                        setExecCmd(preset);
                        handleRunExec(preset);
                      }}
                    >
                      {preset}
                    </button>
                  ))}
                </div>

                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    handleRunExec();
                  }}
                  style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}
                >
                  <input
                    type="text"
                    name="execCmd"
                    aria-label="Command to execute"
                    value={execCmd}
                    onChange={(e) => setExecCmd(e.target.value)}
                    placeholder="Enter command inside container…"
                    className="c220"
                    style={{ flex: 1, fontFamily: 'JetBrains Mono, monospace', fontSize: '13px' }}
                    autoComplete="off"
                    spellCheck={false}
                  />
                  <button type="submit" className="c080" disabled={executing}>
                    {executing ? 'Running…' : 'Execute'}
                  </button>
                </form>

                {execRes && (
                  <div style={{ background: '#080A0E', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '14px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px', fontSize: '11.5px', color: '#8D95A5' }}>
                      <span>$ {execRes.command}</span>
                      <div style={{ display: 'flex', gap: '10px' }}>
                        <span>{execRes.duration_ms}ms</span>
                        <span style={{ color: execRes.exit_code === 0 ? '#5EEAD4' : '#FF8A8A', fontWeight: 600 }}>
                          Exit: {execRes.exit_code}
                        </span>
                      </div>
                    </div>
                    <pre
                      style={{
                        margin: 0,
                        fontSize: '12px',
                        fontFamily: 'JetBrains Mono, monospace',
                        color: '#ECEEF3',
                        maxHeight: '260px',
                        overflowY: 'auto',
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-all',
                      }}
                    >
                      {execRes.output || '(No output)'}
                    </pre>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'compose' && app.source === 'docker' && (
              <div style={{ background: '#101218', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '12px', padding: '20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
                  <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>Docker Compose Inspection</h3>
                  <button
                    type="button"
                    className="c078"
                    disabled={loadingCompose}
                    onClick={loadComposeInfo}
                  >
                    {loadingCompose ? 'Refreshing…' : 'Refresh'}
                  </button>
                </div>

                {loadingCompose ? (
                  <p style={{ color: '#8D95A5', fontSize: '13px' }}>Reading compose metadata…</p>
                ) : composeData?.has_compose ? (
                  <div>
                    <div style={{ display: 'flex', gap: '16px', fontSize: '12.5px', color: '#8D95A5', marginBottom: '14px' }}>
                      <div>Project: <strong style={{ color: '#ECEEF3' }}>{composeData.project}</strong></div>
                      <div>Service: <strong style={{ color: '#8C9EFF' }}>{composeData.service}</strong></div>
                      {composeData.config_file && <div>File: <code style={{ color: '#ECEEF3' }}>{composeData.config_file}</code></div>}
                    </div>

                    {composeData.project && (
                      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap' }}>
                        <span style={{ fontSize: '12px', color: '#8D95A5', marginRight: '4px' }}>Stack Controls:</span>
                        <button
                          type="button"
                          className="c078"
                          style={{ height: '28px', fontSize: '11.5px' }}
                          disabled={executingStackAction !== null}
                          onClick={() => handleStackAction('restart')}
                        >
                          {executingStackAction === 'restart' ? 'Restarting…' : '↻ Restart Stack'}
                        </button>
                        <button
                          type="button"
                          className="c078"
                          style={{ height: '28px', fontSize: '11.5px' }}
                          disabled={executingStackAction !== null}
                          onClick={() => handleStackAction('stop')}
                        >
                          {executingStackAction === 'stop' ? 'Stopping…' : '■ Stop Stack'}
                        </button>
                        <button
                          type="button"
                          className="c078"
                          style={{ height: '28px', fontSize: '11.5px' }}
                          disabled={executingStackAction !== null}
                          onClick={() => handleStackAction('start')}
                        >
                          {executingStackAction === 'start' ? 'Starting…' : '▶ Start Stack'}
                        </button>
                        <button
                          type="button"
                          className="c078"
                          style={{ height: '28px', fontSize: '11.5px', color: '#FF8A8A', borderColor: 'rgba(255,138,138,0.3)' }}
                          disabled={executingStackAction !== null}
                          onClick={() => handleStackAction('down')}
                        >
                          {executingStackAction === 'down' ? 'Downing…' : '▼ Down Stack'}
                        </button>
                      </div>
                    )}

                    {composeData.content ? (
                      <div style={{ position: 'relative' }}>
                        <pre
                          style={{
                            background: '#090B10',
                            border: '1px solid rgba(255,255,255,0.08)',
                            borderRadius: '8px',
                            padding: '16px',
                            fontSize: '12px',
                            fontFamily: 'JetBrains Mono, monospace',
                            color: '#ECEEF3',
                            maxHeight: '340px',
                            overflowY: 'auto',
                            margin: 0,
                          }}
                        >
                          {composeData.content}
                        </pre>
                        <button
                          type="button"
                          className="c078"
                          style={{ position: 'absolute', top: '10px', right: '10px', height: '26px', fontSize: '11px' }}
                          onClick={() => copyToClipboard(composeData.content || '', 'Compose YAML')}
                        >
                          Copy YAML
                        </button>
                      </div>
                    ) : (
                      <p style={{ color: '#8D95A5', fontSize: '13px' }}>{composeData.message || 'Compose file path not readable on this host.'}</p>
                    )}
                  </div>
                ) : (
                  <p style={{ color: '#8D95A5', fontSize: '13px' }}>
                    {composeData?.message || 'This container does not have Docker Compose labels.'}
                  </p>
                )}
              </div>
            )}

            {activeTab === 'env' && (
              <div style={{ background: '#101218', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '12px', padding: '20px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>Environment Variables</h3>
                  {!revealedEnv && (
                    <button
                      type="button"
                      onClick={() => setShowRevealEnvConfirm(true)}
                      disabled={revealingEnv}
                      style={{
                        padding: '6px 12px',
                        borderRadius: '6px',
                        background: 'rgba(140, 158, 255, 0.1)',
                        border: '1px solid rgba(140, 158, 255, 0.3)',
                        color: '#8C9EFF',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      {revealingEnv ? 'Revealing…' : '👁️ Reveal Unmasked Values (Admin)'}
                    </button>
                  )}
                </div>
                {((revealedEnv || inspectData?.env) && (revealedEnv || inspectData?.env).length > 0) ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {(revealedEnv || inspectData.env).map((e: string, i: number) => {
                      const [k, v] = e.split('=', 2);
                      return (
                        <div key={i} style={{ display: 'flex', padding: '8px 12px', background: '#151821', borderRadius: '6px', fontFamily: 'JetBrains Mono, monospace', fontSize: '12px' }}>
                          <span style={{ color: '#8C9EFF', fontWeight: 600, width: '220px' }}>{k}</span>
                          <span style={{ color: '#ECEEF3', flex: 1, wordBreak: 'break-all' }}>{v || ''}</span>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p style={{ color: '#8D95A5', fontSize: '13px' }}>No environment variables recorded or available for host processes.</p>
                )}
              </div>
            )}

            {activeTab === 'volumes' && (
              <div style={{ background: '#101218', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '12px', padding: '20px' }}>
                <h3 style={{ margin: '0 0 16px 0', fontSize: '16px', fontWeight: 600 }}>Volume Mounts</h3>
                {inspectData?.mounts && inspectData.mounts.length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {inspectData.mounts.map((m: any, i: number) => (
                      <div key={i} style={{ padding: '10px 14px', background: '#151821', borderRadius: '8px', fontSize: '13px' }}>
                        <div style={{ color: '#ECEEF3', fontWeight: 600 }}>{m.destination}</div>
                        <div style={{ color: '#8D95A5', fontSize: '12px', marginTop: '4px' }}>Host: {m.source} ({m.type || 'bind'})</div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p style={{ color: '#8D95A5', fontSize: '13px' }}>No volumes mounted for this service.</p>
                )}
              </div>
            )}

            {activeTab === 'health' && (
              <div style={{ background: '#101218', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '12px', padding: '20px' }}>
                <h3 style={{ margin: '0 0 16px 0', fontSize: '16px', fontWeight: 600 }}>Health Check Telemetry</h3>
                <div style={{ display: 'flex', gap: '20px', marginBottom: '20px' }}>
                  <div style={{ padding: '16px', background: '#151821', borderRadius: '10px', flex: 1 }}>
                    <div style={{ fontSize: '12px', color: '#8D95A5' }}>Status</div>
                    <div style={{ fontSize: '20px', fontWeight: 700, color: app.status === 'up' ? '#5EEAD4' : '#FF8A8A', marginTop: '4px' }}>
                      {app.status.toUpperCase()}
                    </div>
                  </div>
                  <div style={{ padding: '16px', background: '#151821', borderRadius: '10px', flex: 1 }}>
                    <div style={{ fontSize: '12px', color: '#8D95A5' }}>Health Checks Recorded</div>
                    <div style={{ fontSize: '20px', fontWeight: 700, color: '#ECEEF3', marginTop: '4px' }}>
                      {healthHistory.length}
                    </div>
                  </div>
                </div>

                <div style={{ fontSize: '13px', color: '#8D95A5', marginBottom: '8px' }}>Recent Latency & Status</div>
                <div style={{ display: 'flex', gap: '4px', height: '48px', alignItems: 'flex-end', background: '#080A0E', padding: '8px', borderRadius: '8px' }}>
                  {healthHistory.map((h, i) => (
                    <div
                      key={i}
                      style={{
                        flex: 1,
                        height: `${Math.min(100, Math.max(10, h.latency_ms * 2))}%`,
                        backgroundColor: h.ok ? '#5EEAD4' : '#FF8A8A',
                        borderRadius: '2px',
                      }}
                      title={`${new Date(h.ts * 1000).toLocaleTimeString()}: ${h.ok ? 'OK' : 'FAIL'} (${h.latency_ms}ms)`}
                    />
                  ))}
                </div>
              </div>
            )}

            {activeTab === 'settings' && (
              <form onSubmit={handleSaveSettings} style={{ background: '#101218', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '12px', padding: '20px' }}>
                <h3 style={{ margin: '0 0 16px 0', fontSize: '16px', fontWeight: 600 }}>App Customization</h3>

                <div style={{ marginBottom: '14px' }}>
                  <label htmlFor="settings-name" style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>Display Name</label>
                  <input
                    id="settings-name"
                    name="customName"
                    type="text"
                    value={customName}
                    onChange={(e) => setCustomName(e.target.value)}
                    autoComplete="off"
                    className="c220"
                    style={{ width: '100%', boxSizing: 'border-box' }}
                  />
                </div>

                <div style={{ marginBottom: '14px' }}>
                  <label htmlFor="settings-category" style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>Category</label>
                  <select
                    id="settings-category"
                    name="customCategory"
                    value={customCategory}
                    onChange={(e) => setCustomCategory(e.target.value)}
                    className="c215"
                    style={{ width: '100%', boxSizing: 'border-box' }}
                  >
                    {categories.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </div>

                <div style={{ marginBottom: '14px' }}>
                  <label htmlFor="settings-tags" style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>Tags (comma-separated)</label>
                  <input
                    id="settings-tags"
                    name="tagsStr"
                    type="text"
                    value={tagsStr}
                    onChange={(e) => setTagsStr(e.target.value)}
                    autoComplete="off"
                    className="c220"
                    style={{ width: '100%', boxSizing: 'border-box' }}
                  />
                </div>

                <div style={{ marginBottom: '20px' }}>
                  <label htmlFor="settings-url-override" style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>URL Override (Reverse proxy / Domain)</label>
                  <input
                    id="settings-url-override"
                    name="urlOverride"
                    type="text"
                    placeholder="https://app.example.com"
                    value={urlOverride}
                    onChange={(e) => setUrlOverride(e.target.value)}
                    autoComplete="off"
                    className="c220"
                    style={{ width: '100%', boxSizing: 'border-box' }}
                  />
                </div>

                <button type="submit" className="c080" disabled={readOnly}>Save Settings</button>
              </form>
            )}
          </div>

          {/* Right Column: Cards */}
          <div className="c208" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Image update card */}
            <div className="c209">
              <div className="c210" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                <span className="c211" style={{ fontWeight: 600, color: '#ECEEF3' }}>Image Update</span>
                <span className="c130" style={{ fontSize: '11px', background: 'rgba(251, 191, 119, 0.15)', color: '#FBBF77', padding: '2px 8px', borderRadius: '6px' }}>
                  {app.id.startsWith('custom:') ? 'Custom app' : app.source !== 'docker' ? 'Docker only'
                    : !updateInfo ? 'Not checked'
                    : updateInfo.known === false ? 'Unknown'
                    : updateInfo.has_update ? 'Update Available' : 'Up to Date'}
                </span>
              </div>
              {app.source === 'docker' ? (
                <>
                  <div className="c212" style={{ fontSize: '12px', color: '#8D95A5', lineHeight: 1.5, marginBottom: '12px' }}>
                    Running <span className="c213" style={{ color: '#ECEEF3', fontFamily: 'JetBrains Mono, monospace' }}>{app.image || app.name}</span>
                  </div>
                  <div className="c216" style={{ display: 'flex', gap: '8px' }}>
                    <button
                      type="button"
                      className="c078"
                      style={{ flex: 1 }}
                      onClick={handleCheckUpdate}
                      disabled={checkingUpdate}
                    >
                      {checkingUpdate ? 'Checking…' : 'Check Now'}
                    </button>
                    {updateInfo?.has_update && (
                      <button
                        type="button"
                        className="c080"
                        style={{ flex: 1 }}
                        onClick={handleApplyUpdate}
                        disabled={applyingUpdate || readOnly}
                      >
                        {applyingUpdate ? 'Applying…' : 'Apply Update'}
                      </button>
                    )}
                  </div>
                </>
              ) : (
                <div className="c212" style={{ fontSize: '12px', color: '#8D95A5', lineHeight: 1.5 }}>
                  {app.id.startsWith('custom:')
                    ? 'Use the Update button in the header to run this app’s update command.'
                    : 'Image updates apply to Docker containers only. This is a host process.'}
                </div>
              )}
            </div>

            {/* Quick Port Info */}
            <div className="c209">
              <div className="c210" style={{ fontWeight: 600, color: '#ECEEF3', marginBottom: '8px' }}>Port Configuration</div>
              <div style={{ fontSize: '13px', color: '#8D95A5', lineHeight: 1.6 }}>
                <div>Host Port: <span style={{ fontFamily: 'JetBrains Mono, monospace', color: '#8C9EFF' }}>:{app.port}</span></div>
                <div>Bind Address: <span style={{ fontFamily: 'JetBrains Mono, monospace', color: '#ECEEF3' }}>{app.bind}</span></div>
                <div>Protocol: <span style={{ fontFamily: 'JetBrains Mono, monospace', color: '#ECEEF3', textTransform: 'uppercase' }}>{app.proto}</span></div>
              </div>
            </div>

            {/* Container / Process Details Card */}
            <div className="c209">
              <div className="c210" style={{ fontWeight: 600, color: '#ECEEF3', marginBottom: '12px' }}>Details</div>
              <div className="c222" style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                <span className="c183" style={{ color: '#8D95A5' }}>Identifier</span>
                <span className="c223" style={{ fontFamily: 'JetBrains Mono, monospace', color: '#ECEEF3' }}>{app.id.slice(0, 16)}</span>
              </div>
              <div className="c222" style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                <span className="c183" style={{ color: '#8D95A5' }}>Source</span>
                <span className="c223" style={{ textTransform: 'capitalize', color: '#ECEEF3' }}>{app.source}</span>
              </div>
              <div className="c222" style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                <span className="c183" style={{ color: '#8D95A5' }}>Category</span>
                <span className="c223" style={{ color: '#ECEEF3' }}>{categories.find(c => c.id === app.category_id)?.name || app.category_id}</span>
              </div>
              <div className="c222" style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', padding: '6px 0' }}>
                <span className="c183" style={{ color: '#8D95A5' }}>Health</span>
                <span className="c223" style={{ color: app.status === 'up' ? '#5EEAD4' : '#FF8A8A' }}>{app.status}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Confirm Dialogs (D-1, D-2, D-11) */}
        <ConfirmDialog
          isOpen={showRollbackConfirm}
          title="Rollback Port Configuration?"
          message="Are you sure you want to rollback this container's port mapping to its previous snapshot? The container will be restarted with original port bindings."
          confirmLabel="Rollback Snapshot"
          isDanger={true}
          onConfirm={confirmRollback}
          onCancel={() => setShowRollbackConfirm(false)}
        />

        <ConfirmDialog
          isOpen={showComposeDownConfirm}
          title="Stop & Remove Compose Stack?"
          message={`Are you sure you want to run down on compose project '${composeData?.project || app.compose_project}'? All containers in this stack will be stopped and removed.`}
          confirmLabel="Run Compose Down"
          isDanger={true}
          onConfirm={() => {
            setShowComposeDownConfirm(false);
            executeStackActionNow('down');
          }}
          onCancel={() => setShowComposeDownConfirm(false)}
        />

        <ConfirmDialog
          isOpen={showRevealEnvConfirm}
          title="Reveal Sensitive Environment Variables?"
          message="Displaying unmasked environment variable values may expose API keys, database credentials, or secret tokens. This action will be recorded in the security audit log."
          confirmLabel="Reveal Secrets"
          isDanger={true}
          onConfirm={handleRevealEnv}
          onCancel={() => setShowRevealEnvConfirm(false)}
        />
      </div>
    </div>
  );
};
