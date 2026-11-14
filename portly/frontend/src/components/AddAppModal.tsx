import React, { useEffect, useState } from 'react';
import { api } from '../api';
import { AppItem, Category } from '../types';

interface AddAppModalProps {
  onClose: () => void;
  categories: Category[];
  availableApps: AppItem[];
  onAppAdded: () => void;
}

export const AddAppModal: React.FC<AddAppModalProps> = ({
  onClose,
  categories,
  availableApps,
  onAppAdded,
}) => {
  const [activeTab, setActiveTab] = useState<'custom' | 'docker' | 'process' | 'external'>('custom');

  // Custom Form fields
  const [name, setName] = useState('');
  const [host, setHost] = useState('localhost');
  const [port, setPort] = useState(4000);
  const [categoryId, setCategoryId] = useState('development');
  const [tags, setTags] = useState('internal');
  const [healthPath, setHealthPath] = useState('/health');
  const [healthInterval, setHealthInterval] = useState(30);
  const [startCmd, setStartCmd] = useState('');
  const [stopCmd, setStopCmd] = useState('auto');
  const [workdir, setWorkdir] = useState('');
  const [logFile, setLogFile] = useState('');
  const [startOnBoot, setStartOnBoot] = useState(false);
  const [pin, setPin] = useState(true);

  // External URL Form fields
  const [extName, setExtName] = useState('');
  const [extUrl, setExtUrl] = useState('');
  const [extCategory, setExtCategory] = useState('infrastructure');
  const [extTags, setExtTags] = useState('external, lan');

  // Manual Docker Form fields
  const [manualDockerName, setManualDockerName] = useState('');
  const [manualDockerPort, setManualDockerPort] = useState(8080);

  // Live port check
  const [portStatus, setPortStatus] = useState<{ free: boolean; used_by: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (activeTab === 'custom') {
      checkPort(port);
    }
  }, [port, activeTab]);

  const checkPort = async (p: number) => {
    try {
      const res = await api.checkPort(p);
      setPortStatus(res);
    } catch {
      setPortStatus(null);
    }
  };

  // Adopt from running host process
  const handleAdoptProcess = (app: AppItem) => {
    setName(app.name);
    setPort(app.port);
    setWorkdir(app.cwd || '');
    setStartCmd(app.cmdline || '');
    setActiveTab('custom');
  };

  // Adopt from Docker container
  const handleAdoptDocker = (app: AppItem) => {
    setName(app.name);
    setPort(app.port);
    setCategoryId(app.category_id || 'infrastructure');
    setTags(app.tags.join(', ') || 'docker, adopted');
    setActiveTab('custom');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      alert('Please enter an app name.');
      return;
    }
    setSubmitting(true);
    try {
      const customId = `custom_${Date.now()}`;
      await api.saveCustomApp({
        id: customId,
        name: name.trim(),
        host,
        port,
        health_path: healthPath,
        health_interval: healthInterval,
        start_cmd: startCmd || undefined,
        stop_cmd: stopCmd === 'auto' ? undefined : stopCmd,
        workdir: workdir || undefined,
        log_file: logFile || undefined,
        start_on_boot: startOnBoot,
        env: {},
      });

      // Override category and tags
      await api.patchApp(`custom:${customId}`, {
        category_id: categoryId,
        tags: tags.split(',').map((t) => t.trim()).filter(Boolean),
        pinned: pin,
      });

      onAppAdded();
      onClose();
    } catch (err: any) {
      alert(`Failed to add app: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleExternalSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!extName.trim() || !extUrl.trim()) {
      alert('Please enter both name and URL.');
      return;
    }
    setSubmitting(true);
    try {
      let parsedPort = 80;
      let parsedHost = 'external';
      try {
        const u = new URL(extUrl);
        parsedHost = u.hostname;
        parsedPort = u.port ? parseInt(u.port) : (u.protocol === 'https:' ? 443 : 80);
      } catch {
        // Fallback port
        parsedPort = 80;
      }

      const customId = `custom_ext_${Date.now()}`;
      await api.saveCustomApp({
        id: customId,
        name: extName.trim(),
        host: parsedHost,
        port: parsedPort,
        health_path: '',
        health_interval: 60,
      });

      await api.patchApp(`custom:${customId}`, {
        category_id: extCategory,
        tags: extTags.split(',').map((t) => t.trim()).filter(Boolean),
        url_override: extUrl.trim(),
        pinned: true,
      });

      onAppAdded();
      onClose();
    } catch (err: any) {
      alert(`Failed to add external URL: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleManualDockerSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualDockerName.trim()) {
      alert('Please enter container name.');
      return;
    }
    setName(manualDockerName.trim());
    setPort(manualDockerPort);
    setCategoryId('infrastructure');
    setTags('docker');
    setActiveTab('custom');
  };

  const dockerApps = availableApps.filter((a) => a.source === 'docker');

  return (
    <div className="modal-backdrop" onClick={onClose} style={{ zIndex: 1200 }}>
      <div
        className="modal-content"
        style={{
          width: '680px',
          maxWidth: '95vw',
          background: '#101218',
          border: '1px solid rgba(255,255,255,0.12)',
          borderRadius: '16px',
          padding: '24px',
          boxSizing: 'border-box',
          overflowY: 'auto',
          maxHeight: '90vh',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="c226" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
          <div>
            <div className="c227" style={{ fontSize: '18px', fontWeight: 600, color: '#ECEEF3' }}>Add custom app</div>
            <div className="c228" style={{ fontSize: '13px', color: '#8D95A5', marginTop: '2px' }}>
              Track an app Portly can’t detect, adopt running services, or bookmark external web dashboards.
            </div>
          </div>
          <button type="button" className="c077" onClick={onClose} aria-label="Close">✕</button>
        </div>

        {/* Tabs */}
        <div className="c093" style={{ marginBottom: '20px' }}>
          <button
            type="button"
            className={activeTab === 'custom' ? 'c094' : 'c095'}
            onClick={() => setActiveTab('custom')}
          >
            Custom app
          </button>
          <button
            type="button"
            className={activeTab === 'process' ? 'c094' : 'c095'}
            onClick={() => setActiveTab('process')}
          >
            From process
          </button>
          <button
            type="button"
            className={activeTab === 'docker' ? 'c094' : 'c095'}
            onClick={() => setActiveTab('docker')}
          >
            From Docker
          </button>
          <button
            type="button"
            className={activeTab === 'external' ? 'c094' : 'c095'}
            onClick={() => setActiveTab('external')}
          >
            External URL
          </button>
        </div>

        {/* Tab 1: From Host Process */}
        {activeTab === 'process' && (
          <div style={{ marginBottom: '20px', maxHeight: '320px', overflowY: 'auto' }}>
            <div style={{ fontSize: '13px', color: '#8D95A5', marginBottom: '10px' }}>
              Select a running local process to adopt into Portly management:
            </div>
            {availableApps.filter((a) => a.source === 'host').length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', color: '#8D95A5', fontSize: '13px' }}>
                No host processes discovered yet.
              </div>
            ) : (
              availableApps.filter((a) => a.source === 'host').map((h) => (
                <div
                  key={h.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '10px 14px',
                    background: '#151821',
                    borderRadius: '8px',
                    marginBottom: '6px',
                  }}
                >
                  <div>
                    <span style={{ fontWeight: 600, color: '#ECEEF3' }}>{h.name}</span>
                    <span style={{ fontFamily: 'JetBrains Mono, monospace', color: '#8C9EFF', marginLeft: '8px' }}>:{h.port}</span>
                    <div style={{ fontSize: '11px', color: '#8D95A5', marginTop: '2px' }}>
                      PID {h.pid} · {h.bind} · {h.process_name || 'process'}
                    </div>
                  </div>
                  <button
                    type="button"
                    className="c078"
                    style={{ height: '30px', fontSize: '12px' }}
                    onClick={() => handleAdoptProcess(h)}
                  >
                    Adopt
                  </button>
                </div>
              ))
            )}
          </div>
        )}

        {/* Tab 2: From Docker Container */}
        {activeTab === 'docker' && (
          <div style={{ marginBottom: '20px', maxHeight: '320px', overflowY: 'auto' }}>
            <div style={{ fontSize: '13px', color: '#8D95A5', marginBottom: '10px' }}>
              Discovered Docker containers available for adoption or customization:
            </div>
            {dockerApps.length > 0 ? (
              dockerApps.map((d) => (
                <div
                  key={d.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '10px 14px',
                    background: '#151821',
                    borderRadius: '8px',
                    marginBottom: '6px',
                  }}
                >
                  <div>
                    <span style={{ fontWeight: 600, color: '#ECEEF3' }}>{d.name}</span>
                    <span style={{ fontFamily: 'JetBrains Mono, monospace', color: '#5EEAD4', marginLeft: '8px' }}>:{d.port}</span>
                    <div style={{ fontSize: '11px', color: '#8D95A5', marginTop: '2px' }}>
                      Image: {d.image || d.container_name} · Status: {d.status}
                    </div>
                  </div>
                  <button
                    type="button"
                    className="c078"
                    style={{ height: '30px', fontSize: '12px' }}
                    onClick={() => handleAdoptDocker(d)}
                  >
                    Adopt
                  </button>
                </div>
              ))
            ) : (
              <div style={{ padding: '20px', background: '#151821', borderRadius: '10px' }}>
                <p style={{ margin: '0 0 12px 0', fontSize: '13px', color: '#FBBF77' }}>
                  No active Docker containers discovered on socket. You can specify a container manually:
                </p>
                <form onSubmit={handleManualDockerSubmit} style={{ display: 'flex', gap: '10px' }}>
                  <input
                    type="text"
                    placeholder="Container Name (e.g. postgres-prod)"
                    value={manualDockerName}
                    onChange={(e) => setManualDockerName(e.target.value)}
                    className="c220"
                    style={{ flex: 2 }}
                    required
                  />
                  <input
                    type="number"
                    placeholder="Port"
                    value={manualDockerPort}
                    onChange={(e) => setManualDockerPort(parseInt(e.target.value) || 0)}
                    className="c220"
                    style={{ flex: 1 }}
                    required
                  />
                  <button type="submit" className="c080">Pre-fill</button>
                </form>
              </div>
            )}
          </div>
        )}

        {/* Tab 3: External URL */}
        {activeTab === 'external' && (
          <form onSubmit={handleExternalSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ fontSize: '13px', color: '#8D95A5' }}>
              Add remote web dashboards, NAS portals, router admin pages, or cloud services to Portly:
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>App / Dashboard Name</label>
              <input
                type="text"
                placeholder="e.g. Synology DSM or Proxmox VE"
                value={extName}
                onChange={(e) => setExtName(e.target.value)}
                className="c220"
                style={{ width: '100%', boxSizing: 'border-box' }}
                required
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>Full Target URL</label>
              <input
                type="url"
                placeholder="https://192.168.1.50:8006 or https://nas.local:5001"
                value={extUrl}
                onChange={(e) => setExtUrl(e.target.value)}
                className="c220"
                style={{ width: '100%', boxSizing: 'border-box' }}
                required
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>Category</label>
                <select
                  value={extCategory}
                  onChange={(e) => setExtCategory(e.target.value)}
                  className="c215"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                >
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>Tags</label>
                <input
                  type="text"
                  value={extTags}
                  onChange={(e) => setExtTags(e.target.value)}
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
              <button type="button" className="c078" onClick={onClose}>Cancel</button>
              <button type="submit" className="c080" disabled={submitting}>
                {submitting ? 'Saving...' : 'Add Bookmark'}
              </button>
            </div>
          </form>
        )}

        {/* Tab 0: Custom App Form */}
        {activeTab === 'custom' && (
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Name & Icon */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 120px', gap: '14px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>Name</label>
                <input
                  type="text"
                  placeholder="Billing API"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                  required
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>Icon</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <div
                    className="c233"
                    style={{
                      width: '34px',
                      height: '34px',
                      borderRadius: '8px',
                      background: '#8C9EFF',
                      color: '#0A0B0F',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontWeight: 700,
                    }}
                  >
                    {(name || 'A').charAt(0).toUpperCase()}
                  </div>
                </div>
              </div>
            </div>

            {/* Network: Host & Port */}
            <div style={{ fontSize: '13px', fontWeight: 600, color: '#ECEEF3', marginTop: '6px' }}>Network</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>Host</label>
                <input
                  type="text"
                  value={host}
                  onChange={(e) => setHost(e.target.value)}
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>Port</label>
                <input
                  type="number"
                  value={port}
                  onChange={(e) => setPort(parseInt(e.target.value) || 0)}
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
            </div>

            {/* Live Port Check */}
            {portStatus && (
              <div style={{ fontSize: '12px', color: portStatus.free ? '#5EEAD4' : '#FF8A8A', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span>{portStatus.free ? '✓' : '✗'}</span>
                <span>
                  {portStatus.free
                    ? `Port ${port} is free · opens http://${host}:${port}`
                    : `Port ${port} is in use: ${portStatus.used_by}`}
                </span>
              </div>
            )}

            {/* Organize: Category & Tags */}
            <div style={{ fontSize: '13px', fontWeight: 600, color: '#ECEEF3', marginTop: '6px' }}>Organize</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>Category</label>
                <select
                  value={categoryId}
                  onChange={(e) => setCategoryId(e.target.value)}
                  className="c215"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                >
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>Tags (comma-separated)</label>
                <input
                  type="text"
                  placeholder="internal, billing"
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
            </div>

            {/* Run Controls */}
            <div style={{ fontSize: '13px', fontWeight: 600, color: '#ECEEF3', marginTop: '6px' }}>Run controls</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>Start command</label>
                <input
                  type="text"
                  placeholder="npm run start or python app.py"
                  value={startCmd}
                  onChange={(e) => setStartCmd(e.target.value)}
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>Stop command</label>
                <input
                  type="text"
                  placeholder="auto (terminate process)"
                  value={stopCmd}
                  onChange={(e) => setStopCmd(e.target.value)}
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>Working directory</label>
                <input
                  type="text"
                  placeholder="C:\projects\my-app"
                  value={workdir}
                  onChange={(e) => setWorkdir(e.target.value)}
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '6px' }}>Log file path</label>
                <input
                  type="text"
                  placeholder="C:\projects\my-app\app.log"
                  value={logFile}
                  onChange={(e) => setLogFile(e.target.value)}
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
            </div>

            {/* Switches */}
            <div style={{ display: 'flex', gap: '20px', marginTop: '6px' }}>
              <label style={{ fontSize: '13px', color: '#ECEEF3', display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                <input type="checkbox" checked={startOnBoot} onChange={(e) => setStartOnBoot(e.target.checked)} className="c173" />
                Start on boot
              </label>
              <label style={{ fontSize: '13px', color: '#ECEEF3', display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                <input type="checkbox" checked={pin} onChange={(e) => setPin(e.target.checked)} className="c173" />
                Pin to favorites
              </label>
            </div>

            {/* Footer */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '14px', borderTop: '1px solid rgba(255,255,255,0.07)', paddingTop: '16px' }}>
              <span style={{ fontSize: '12px', color: '#8D95A5' }}>Saved to your Portly SQLite store.</span>
              <div style={{ display: 'flex', gap: '10px' }}>
                <button type="button" className="c078" onClick={onClose}>Cancel</button>
                <button type="submit" className="c080" disabled={submitting}>
                  {submitting ? 'Adding...' : 'Add app'}
                </button>
              </div>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
