import React, { useCallback, useEffect, useState } from 'react';
import { Icon } from './Icon';
import { api } from '../api';
import { DockerSystemDf, SystemStats } from '../types';
import { useFocusTrap } from '../hooks/useFocusTrap';
import { useToast } from './Toast';
import { ConfirmDialog } from './ConfirmDialog';

interface SystemDrawerProps {
  onClose: () => void;
  defaultSection?: string;
}

const SECTION_IDS: Record<string, string> = {
  cpu: 'sys-cpu',
  memory: 'sys-memory',
  disk: 'sys-disk',
  network: 'sys-network',
  containers: 'sys-containers',
  listening: 'sys-overview',
};

export const SystemDrawer: React.FC<SystemDrawerProps> = ({ onClose, defaultSection }) => {
  const { success, error } = useToast();
  const containerRef = useFocusTrap<HTMLDivElement>(true, onClose);
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [dockerDf, setDockerDf] = useState<DockerSystemDf | null>(null);
  const [pruning, setPruning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showPruneConfirm, setShowPruneConfirm] = useState(false);

  const fetchingRef = React.useRef(false);
  const didScrollRef = React.useRef(false);

  // StatsStrip tiles pass a section key; jump to the matching panel once stats
  // have rendered so the drilldown lands on something real.
  useEffect(() => {
    if (!defaultSection || didScrollRef.current || !stats) return;
    const id = SECTION_IDS[defaultSection];
    if (!id) return;
    didScrollRef.current = true;
    document.getElementById(id)?.scrollIntoView({ block: 'start' });
  }, [defaultSection, stats]);

  const loadStats = useCallback(async () => {
    try {
      const data = await api.getSystemStats();
      setStats(data);
    } catch {} finally {
      setLoading(false);
    }
  }, []);

  const loadDockerStats = useCallback(async () => {
    try {
      const df = await api.getDockerSystemDf();
      setDockerDf(df);
    } catch {}
  }, []);

  const loadAll = useCallback(async () => {
    // Skip ticks while a fetch is in flight: docker df can be seconds-slow.
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    try {
      await Promise.all([loadStats(), loadDockerStats()]);
    } finally {
      fetchingRef.current = false;
    }
  }, [loadStats, loadDockerStats]);

  useEffect(() => {
    void loadAll();
    const interval = setInterval(() => { void loadAll(); }, 4000);
    return () => clearInterval(interval);
  }, [loadAll]);

  const handlePrune = () => {
    setShowPruneConfirm(true);
  };

  const confirmPrune = async () => {
    setShowPruneConfirm(false);
    setPruning(true);
    try {
      const res = await api.pruneDockerSystem();
      success(`Docker system pruned! Reclaimed ${res.space_reclaimed_mb} MB.`);
      loadDockerStats();
    } catch (e: any) {
      error(`Prune failed: ${e.message}`);
    } finally {
      setPruning(false);
    }
  };

  return (
    <div className="drawer-backdrop" onClick={onClose} style={{ zIndex: 1250 }}>
      <div
        ref={containerRef}
        className="drawer-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="system-drawer-title"
        style={{
          width: '540px',
          background: 'var(--surface-1)',
          borderLeft: '1px solid rgba(255,255,255,0.08)',
          padding: '24px',
          display: 'flex',
          flexDirection: 'column',
          gap: '20px',
          boxSizing: 'border-box',
          overflowY: 'auto',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.07)', paddingBottom: '14px' }}>
          <div>
            <h2 id="system-drawer-title" style={{ margin: 0, fontSize: '18px', fontWeight: 600, color: 'var(--text)' }}>System Telemetry & Hardware</h2>
            <div style={{ fontSize: '12px', color: 'var(--muted)', marginTop: '2px' }}>
              {stats?.hostname || 'Localhost'} · {stats?.platform || 'Host'}
            </div>
          </div>
          <button type="button" className="c077" onClick={onClose} aria-label="Close"><Icon name="x" size={13} /></button>
        </div>

        {/* Privilege caveat: no backend capability flag exists yet, so explain it inline. */}
        <div role="note" style={{ padding: '10px 14px', borderRadius: '10px', background: 'rgba(251, 191, 119, 0.08)', border: '1px solid rgba(251, 191, 119, 0.22)', color: 'var(--warning)', fontSize: '12px', lineHeight: 1.5 }}>
          <strong>Limited host visibility (not running as root)</strong>
          <div style={{ color: 'var(--muted)', marginTop: '4px' }}>
            Without elevated privileges, Portly may not see all host processes, privileged ports (&lt;1024), or container details. Metrics may be unavailable or stale.
          </div>
        </div>

        {loading && !stats ? (
          <div style={{ color: 'var(--muted)', textAlign: 'center', paddingTop: '40px' }}>Loading system telemetry…</div>
        ) : stats ? (
          <>
            {stats.untrusted_proxy_detected && (
              <div role="note" style={{ padding: '10px 14px', borderRadius: '10px', background: 'rgba(251, 191, 119, 0.08)', border: '1px solid rgba(251, 191, 119, 0.22)', color: 'var(--warning)', fontSize: '12px', lineHeight: 1.5 }}>
                <strong>Behind a proxy?</strong>
                <div style={{ color: 'var(--muted)', marginTop: '4px' }}>
                  Proxy headers were seen but <code>PORTLY_TRUSTED_PROXIES</code> is not set. Client IPs (login lockout) and Secure cookies are unreliable. Set it to your proxy address.
                </div>
              </div>
            )}

            {/* Overview Box */}
            <div id="sys-overview" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div style={{ padding: '14px', background: 'var(--surface-2)', borderRadius: '10px' }}>
                <div style={{ fontSize: '12px', color: 'var(--muted)' }}>Host Uptime</div>
                <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text)', marginTop: '4px' }}>{stats.uptime}</div>
              </div>
              <div style={{ padding: '14px', background: 'var(--surface-2)', borderRadius: '10px' }}>
                <div style={{ fontSize: '12px', color: 'var(--muted)' }}>Total Cores</div>
                <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text)', marginTop: '4px' }}>
                  {stats.cpu_per_core?.length || 1} Cores
                </div>
              </div>
            </div>

            {/* Per Core CPU Bars */}
            <div id="sys-cpu" style={{ background: 'var(--surface-2)', borderRadius: '12px', padding: '16px' }}>
              <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', marginBottom: '12px' }}>CPU Load Per Core</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(100px, 1fr))', gap: '8px' }}>
                {stats.cpu_per_core?.map((pct, idx) => (
                  <div key={idx} style={{ background: 'var(--surface-1)', padding: '8px', borderRadius: '6px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--muted)', marginBottom: '4px' }}>
                      <span>Core {idx}</span>
                      <span style={{ color: 'var(--text)' }}>{pct}%</span>
                    </div>
                    <div style={{ height: '4px', background: 'rgba(255,255,255,0.08)', borderRadius: '2px', overflow: 'hidden' }}>
                      <div style={{ width: `${Math.min(100, Math.max(2, pct))}%`, height: '100%', background: 'var(--accent)' }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Memory & Swap */}
            <div id="sys-memory" style={{ background: 'var(--surface-2)', borderRadius: '12px', padding: '16px' }}>
              <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', marginBottom: '12px' }}>Memory & Swap Allocation</div>
              <div style={{ marginBottom: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                  <span style={{ color: 'var(--text)' }}>Physical RAM: {stats.memory?.used_gb} GB of {stats.memory?.total_gb} GB</span>
                  <span style={{ color: 'var(--success)' }}>{stats.memory?.percent}%</span>
                </div>
                <div style={{ height: '6px', background: 'rgba(255,255,255,0.08)', borderRadius: '3px', overflow: 'hidden' }}>
                  <div style={{ width: `${stats.memory?.percent || 0}%`, height: '100%', background: 'var(--success)' }} />
                </div>
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                  <span style={{ color: 'var(--text)' }}>Swap Space: {stats.swap?.used_gb} GB of {stats.swap?.total_gb} GB</span>
                  <span style={{ color: 'var(--warning)' }}>{stats.swap?.percent}%</span>
                </div>
                <div style={{ height: '6px', background: 'rgba(255,255,255,0.08)', borderRadius: '3px', overflow: 'hidden' }}>
                  <div style={{ width: `${stats.swap?.percent || 0}%`, height: '100%', background: 'var(--warning)' }} />
                </div>
              </div>
            </div>

            {/* Disks */}
            <div id="sys-disk" style={{ background: 'var(--surface-2)', borderRadius: '12px', padding: '16px' }}>
              <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', marginBottom: '12px' }}>Disk Storage & Mounts</div>
              {stats.host_visible === false && (
                <div role="note" style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '10px' }}>
                  Container disk shown. Mount <code>/:/hostfs:ro</code> and set <code>PORTLY_HOSTFS=/hostfs</code> for host numbers.
                </div>
              )}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {stats.disks?.map((d, i) => (
                  <div key={i} style={{ background: 'var(--surface-1)', padding: '10px', borderRadius: '8px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '6px' }}>
                      <span style={{ fontWeight: 600, color: 'var(--text)' }}>{d.mountpoint} ({d.device})</span>
                      <span style={{ color: 'var(--muted)' }}>{d.used_gb} GB / {d.total_gb} GB ({d.percent}%)</span>
                    </div>
                    <div style={{ height: '6px', background: 'rgba(255,255,255,0.08)', borderRadius: '3px', overflow: 'hidden' }}>
                      <div style={{ width: `${d.percent}%`, height: '100%', background: d.percent > 90 ? 'var(--danger)' : 'var(--accent)' }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Docker Storage & System Hygiene */}
            {dockerDf?.available && (
              <div id="sys-containers" style={{ background: 'var(--surface-2)', borderRadius: '12px', padding: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span>Docker Storage & Hygiene</span>
                    <span style={{ fontSize: '11px', background: 'rgba(94, 234, 212, 0.15)', color: 'var(--success)', padding: '2px 8px', borderRadius: '6px' }}>
                      Engine
                    </span>
                  </div>
                  <button
                    type="button"
                    className="c078"
                    style={{ height: '26px', fontSize: '11px', color: 'var(--danger)', borderColor: 'rgba(255,138,138,0.3)', display: 'inline-flex', alignItems: 'center', gap: '5px' }}
                    disabled={pruning}
                    onClick={handlePrune}
                  >
                    <Icon name="trash" size={12} />
                    <span>{pruning ? 'Pruning…' : 'Prune Unused Space'}</span>
                  </button>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '12px' }}>
                  <div style={{ background: 'var(--surface-1)', padding: '10px', borderRadius: '8px' }}>
                    <div style={{ fontSize: '11px', color: 'var(--muted)' }}>Docker Images</div>
                    <div style={{ fontSize: '16px', fontWeight: 700, color: 'var(--text)', marginTop: '4px' }}>
                      {dockerDf.images_count}
                    </div>
                  </div>
                  <div style={{ background: 'var(--surface-1)', padding: '10px', borderRadius: '8px' }}>
                    <div style={{ fontSize: '11px', color: 'var(--muted)' }}>Volumes</div>
                    <div style={{ fontSize: '16px', fontWeight: 700, color: 'var(--text)', marginTop: '4px' }}>
                      {dockerDf.volumes_count}
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--muted)', background: 'var(--surface-1)', padding: '10px', borderRadius: '8px' }}>
                  <span>Total Docker Disk: <strong style={{ color: 'var(--text)' }}>{dockerDf.total_size_mb > 1024 ? `${(dockerDf.total_size_mb / 1024).toFixed(1)} GB` : `${dockerDf.total_size_mb} MB`}</strong></span>
                  <span>Reclaimable: <strong style={{ color: 'var(--success)' }}>{dockerDf.total_reclaimable_mb > 1024 ? `${(dockerDf.total_reclaimable_mb / 1024).toFixed(1)} GB` : `${dockerDf.total_reclaimable_mb} MB`}</strong></span>
                </div>
              </div>
            )}

            {/* Network Interfaces */}
            <div id="sys-network" style={{ background: 'var(--surface-2)', borderRadius: '12px', padding: '16px' }}>
              <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', marginBottom: '12px' }}>Network Interfaces</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {stats.interfaces?.filter(iface => iface.ip).map((iface, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 10px', background: 'var(--surface-1)', borderRadius: '6px', fontSize: '12px' }}>
                    <span style={{ color: 'var(--text)', fontWeight: 600 }}>{iface.name}</span>
                    <span style={{ fontFamily: 'JetBrains Mono, monospace', color: 'var(--accent)' }}>{iface.ip}</span>
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : null}

        <ConfirmDialog
          isOpen={showPruneConfirm}
          title="Prune Docker System?"
          message="Are you sure you want to prune dangling images, stopped containers, and unused volumes to reclaim host disk space? This operation cannot be undone."
          confirmLabel="Prune System"
          isDanger={true}
          onConfirm={confirmPrune}
          onCancel={() => setShowPruneConfirm(false)}
        />
      </div>
    </div>
  );
};
