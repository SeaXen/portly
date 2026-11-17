import React, { useEffect, useState } from 'react';
import { api } from '../api';
import { DockerSystemDf, SystemStats } from '../types';
import { useToast } from './Toast';
import { ConfirmDialog } from './ConfirmDialog';

interface SystemDrawerProps {
  onClose: () => void;
  defaultSection?: string;
}

export const SystemDrawer: React.FC<SystemDrawerProps> = ({ onClose, defaultSection }) => {
  const { success, error } = useToast();
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [dockerDf, setDockerDf] = useState<DockerSystemDf | null>(null);
  const [pruning, setPruning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showPruneConfirm, setShowPruneConfirm] = useState(false);

  useEffect(() => {
    loadStats();
    loadDockerStats();
    const interval = setInterval(() => {
      loadStats();
      loadDockerStats();
    }, 4000);
    return () => clearInterval(interval);
  }, []);

  const loadStats = async () => {
    try {
      const data = await api.getSystemStats();
      setStats(data);
    } catch {} finally {
      setLoading(false);
    }
  };

  const loadDockerStats = async () => {
    try {
      const df = await api.getDockerSystemDf();
      setDockerDf(df);
    } catch {}
  };

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
        className="drawer-panel"
        style={{
          width: '540px',
          background: '#101218',
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
            <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 600, color: '#ECEEF3' }}>System Telemetry & Hardware</h2>
            <div style={{ fontSize: '12px', color: '#8D95A5', marginTop: '2px' }}>
              {stats?.hostname || 'Localhost'} · {stats?.platform || 'Host'}
            </div>
          </div>
          <button type="button" className="c077" onClick={onClose} aria-label="Close">✕</button>
        </div>

        {loading && !stats ? (
          <div style={{ color: '#8D95A5', textAlign: 'center', paddingTop: '40px' }}>Loading system telemetry…</div>
        ) : stats ? (
          <>
            {/* Overview Box */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div style={{ padding: '14px', background: '#151821', borderRadius: '10px' }}>
                <div style={{ fontSize: '12px', color: '#8D95A5' }}>Host Uptime</div>
                <div style={{ fontSize: '18px', fontWeight: 700, color: '#ECEEF3', marginTop: '4px' }}>{stats.uptime}</div>
              </div>
              <div style={{ padding: '14px', background: '#151821', borderRadius: '10px' }}>
                <div style={{ fontSize: '12px', color: '#8D95A5' }}>Total Cores</div>
                <div style={{ fontSize: '18px', fontWeight: 700, color: '#ECEEF3', marginTop: '4px' }}>
                  {stats.cpu_per_core?.length || 1} Cores
                </div>
              </div>
            </div>

            {/* Per Core CPU Bars */}
            <div style={{ background: '#151821', borderRadius: '12px', padding: '16px' }}>
              <div style={{ fontSize: '13px', fontWeight: 600, color: '#ECEEF3', marginBottom: '12px' }}>CPU Load Per Core</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(100px, 1fr))', gap: '8px' }}>
                {stats.cpu_per_core?.map((pct, idx) => (
                  <div key={idx} style={{ background: '#101218', padding: '8px', borderRadius: '6px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#8D95A5', marginBottom: '4px' }}>
                      <span>Core {idx}</span>
                      <span style={{ color: '#ECEEF3' }}>{pct}%</span>
                    </div>
                    <div style={{ height: '4px', background: 'rgba(255,255,255,0.08)', borderRadius: '2px', overflow: 'hidden' }}>
                      <div style={{ width: `${Math.min(100, Math.max(2, pct))}%`, height: '100%', background: '#8C9EFF' }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Memory & Swap */}
            <div style={{ background: '#151821', borderRadius: '12px', padding: '16px' }}>
              <div style={{ fontSize: '13px', fontWeight: 600, color: '#ECEEF3', marginBottom: '12px' }}>Memory & Swap Allocation</div>
              <div style={{ marginBottom: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                  <span style={{ color: '#ECEEF3' }}>Physical RAM: {stats.memory?.used_gb} GB of {stats.memory?.total_gb} GB</span>
                  <span style={{ color: '#5EEAD4' }}>{stats.memory?.percent}%</span>
                </div>
                <div style={{ height: '6px', background: 'rgba(255,255,255,0.08)', borderRadius: '3px', overflow: 'hidden' }}>
                  <div style={{ width: `${stats.memory?.percent || 0}%`, height: '100%', background: '#5EEAD4' }} />
                </div>
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                  <span style={{ color: '#ECEEF3' }}>Swap Space: {stats.swap?.used_gb} GB of {stats.swap?.total_gb} GB</span>
                  <span style={{ color: '#FBBF77' }}>{stats.swap?.percent}%</span>
                </div>
                <div style={{ height: '6px', background: 'rgba(255,255,255,0.08)', borderRadius: '3px', overflow: 'hidden' }}>
                  <div style={{ width: `${stats.swap?.percent || 0}%`, height: '100%', background: '#FBBF77' }} />
                </div>
              </div>
            </div>

            {/* Disks */}
            <div style={{ background: '#151821', borderRadius: '12px', padding: '16px' }}>
              <div style={{ fontSize: '13px', fontWeight: 600, color: '#ECEEF3', marginBottom: '12px' }}>Disk Storage & Mounts</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {stats.disks?.map((d, i) => (
                  <div key={i} style={{ background: '#101218', padding: '10px', borderRadius: '8px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '6px' }}>
                      <span style={{ fontWeight: 600, color: '#ECEEF3' }}>{d.mountpoint} ({d.device})</span>
                      <span style={{ color: '#8D95A5' }}>{d.used_gb} GB / {d.total_gb} GB ({d.percent}%)</span>
                    </div>
                    <div style={{ height: '6px', background: 'rgba(255,255,255,0.08)', borderRadius: '3px', overflow: 'hidden' }}>
                      <div style={{ width: `${d.percent}%`, height: '100%', background: d.percent > 90 ? '#FF8A8A' : '#8C9EFF' }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Docker Storage & System Hygiene */}
            {dockerDf?.available && (
              <div style={{ background: '#151821', borderRadius: '12px', padding: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: '#ECEEF3', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span>Docker Storage & Hygiene</span>
                    <span style={{ fontSize: '11px', background: 'rgba(94, 234, 212, 0.15)', color: '#5EEAD4', padding: '2px 8px', borderRadius: '6px' }}>
                      Engine
                    </span>
                  </div>
                  <button
                    type="button"
                    className="c078"
                    style={{ height: '26px', fontSize: '11px', color: '#FF8A8A', borderColor: 'rgba(255,138,138,0.3)' }}
                    disabled={pruning}
                    onClick={handlePrune}
                  >
                    {pruning ? 'Pruning…' : '🧹 Prune Unused Space'}
                  </button>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '12px' }}>
                  <div style={{ background: '#101218', padding: '10px', borderRadius: '8px' }}>
                    <div style={{ fontSize: '11px', color: '#8D95A5' }}>Docker Images</div>
                    <div style={{ fontSize: '16px', fontWeight: 700, color: '#ECEEF3', marginTop: '4px' }}>
                      {dockerDf.images_count}
                    </div>
                  </div>
                  <div style={{ background: '#101218', padding: '10px', borderRadius: '8px' }}>
                    <div style={{ fontSize: '11px', color: '#8D95A5' }}>Volumes</div>
                    <div style={{ fontSize: '16px', fontWeight: 700, color: '#ECEEF3', marginTop: '4px' }}>
                      {dockerDf.volumes_count}
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#8D95A5', background: '#101218', padding: '10px', borderRadius: '8px' }}>
                  <span>Total Docker Disk: <strong style={{ color: '#ECEEF3' }}>{dockerDf.total_size_mb > 1024 ? `${(dockerDf.total_size_mb / 1024).toFixed(1)} GB` : `${dockerDf.total_size_mb} MB`}</strong></span>
                  <span>Reclaimable: <strong style={{ color: '#5EEAD4' }}>{dockerDf.total_reclaimable_mb > 1024 ? `${(dockerDf.total_reclaimable_mb / 1024).toFixed(1)} GB` : `${dockerDf.total_reclaimable_mb} MB`}</strong></span>
                </div>
              </div>
            )}

            {/* Network Interfaces */}
            <div style={{ background: '#151821', borderRadius: '12px', padding: '16px' }}>
              <div style={{ fontSize: '13px', fontWeight: 600, color: '#ECEEF3', marginBottom: '12px' }}>Network Interfaces</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {stats.interfaces?.filter(iface => iface.ip).map((iface, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 10px', background: '#101218', borderRadius: '6px', fontSize: '12px' }}>
                    <span style={{ color: '#ECEEF3', fontWeight: 600 }}>{iface.name}</span>
                    <span style={{ fontFamily: 'JetBrains Mono, monospace', color: '#8C9EFF' }}>{iface.ip}</span>
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
