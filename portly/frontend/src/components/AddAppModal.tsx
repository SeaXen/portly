import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { AppItem, Category, PreflightResponse } from '../types';
import { useFocusTrap } from '../hooks/useFocusTrap';
import { useToast } from './Toast';
import { Icon } from './Icon';

interface AddAppModalProps {
  onClose: () => void;
  categories: Category[];
  availableApps: AppItem[];
  onAppAdded: () => void;
  initialAdoptApp?: AppItem | null;
}

export const AddAppModal: React.FC<AddAppModalProps> = ({
  onClose,
  categories,
  availableApps,
  onAppAdded,
  initialAdoptApp,
}) => {
  const { success, error, warning } = useToast();
  const [activeTab, setActiveTab] = useState<'custom' | 'docker' | 'process' | 'external' | 'deploy' | 'preflight'>('custom');

  // Custom Form fields
  const [name, setName] = useState('');
  const [host, setHost] = useState('localhost');
  const [port, setPort] = useState(4000);
  const [categoryId, setCategoryId] = useState('development');
  const [tags, setTags] = useState('internal');
  const [healthPath, setHealthPath] = useState('/health');
  const [healthInterval, setHealthInterval] = useState(30);
  const [expectedStatus, setExpectedStatus] = useState('200,204,301,302');
  const [customHeaders, setCustomHeaders] = useState('');
  const [startCmd, setStartCmd] = useState('');
  const [stopCmd, setStopCmd] = useState('auto');
  const [workdir, setWorkdir] = useState('');
  const [logFile, setLogFile] = useState('');
  const [startOnBoot, setStartOnBoot] = useState(false);
  const [pin, setPin] = useState(true);

  useEffect(() => {
    if (initialAdoptApp) {
      setActiveTab('custom');
      setName(initialAdoptApp.name || initialAdoptApp.process_name || 'Adopted App');
      setPort(initialAdoptApp.port || 3000);
      setHost(initialAdoptApp.bind === '0.0.0.0' ? 'localhost' : initialAdoptApp.bind);
      setStartCmd(initialAdoptApp.cmdline || '');
      setWorkdir(initialAdoptApp.cwd || '');
      setTags('adopted, host');
      setHealthPath('/');
    }
  }, [initialAdoptApp]);

  // Preflight check tab state (D-10, F-5)
  const [preflightMode, setPreflightMode] = useState<'command' | 'compose' | 'ports'>('command');
  const [preflightInput, setPreflightInput] = useState('docker run -d -p 8080:80 -p 3306:3306 nginx');
  const [preflightResult, setPreflightResult] = useState<PreflightResponse | null>(null);
  const [preflightChecking, setPreflightChecking] = useState(false);

  // External URL Form fields
  const [extName, setExtName] = useState('');
  const [extUrl, setExtUrl] = useState('');
  const [extCategory, setExtCategory] = useState('infrastructure');
  const [extTags, setExtTags] = useState('external, lan');

  // Manual Docker Form fields
  const [manualDockerName, setManualDockerName] = useState('');
  const [manualDockerPort, setManualDockerPort] = useState(8080);

  // Deploy Container fields
  const [deployImage, setDeployImage] = useState('redis:7-alpine');
  const [deployName, setDeployName] = useState('my-redis');
  const [deployHostPort, setDeployHostPort] = useState(6379);
  const [deployContainerPort, setDeployContainerPort] = useState('6379/tcp');
  const [deployEnv, setDeployEnv] = useState('');
  const [deployRestart] = useState('unless-stopped');
  const [deploying, setDeploying] = useState(false);
  const [deployPortStatus, setDeployPortStatus] = useState<{ free: boolean; used_by: string } | null>(null);

  const PRESET_TEMPLATES = [
    { label: 'PostgreSQL', image: 'postgres:16-alpine', name: 'postgres', hostPort: 5432, containerPort: '5432/tcp', env: 'POSTGRES_PASSWORD=postgres' },
    { label: 'Redis', image: 'redis:7-alpine', name: 'redis', hostPort: 6379, containerPort: '6379/tcp', env: '' },
    { label: 'Nginx', image: 'nginx:alpine', name: 'nginx', hostPort: 8080, containerPort: '80/tcp', env: '' },
    { label: 'Uptime Kuma', image: 'louislam/uptime-kuma:1', name: 'uptime-kuma', hostPort: 3001, containerPort: '3001/tcp', env: '' },
    { label: 'Nextcloud', image: 'nextcloud:apache', name: 'nextcloud', hostPort: 8088, containerPort: '80/tcp', env: '' },
  ];

  // Live port check
  const [portStatus, setPortStatus] = useState<{ free: boolean; used_by: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const portReqRef = useRef(0);
  const deployPortReqRef = useRef(0);

  useEffect(() => {
    if (activeTab === 'custom') {
      checkPort(port);
    } else if (activeTab === 'deploy') {
      checkDeployPort(deployHostPort);
    }
  }, [port, deployHostPort, activeTab]);

  const checkPort = async (p: number) => {
    const req = ++portReqRef.current;
    try {
      const res = await api.checkPort(p);
      if (req === portReqRef.current) setPortStatus(res);
    } catch {
      if (req === portReqRef.current) setPortStatus(null);
    }
  };

  const checkDeployPort = async (p: number) => {
    const req = ++deployPortReqRef.current;
    try {
      const res = await api.checkPort(p);
      if (req === deployPortReqRef.current) setDeployPortStatus(res);
    } catch {
      if (req === deployPortReqRef.current) setDeployPortStatus(null);
    }
  };

  const handleSelectPreset = (p: typeof PRESET_TEMPLATES[0]) => {
    setDeployImage(p.image);
    setDeployName(p.name);
    setDeployHostPort(p.hostPort);
    setDeployContainerPort(p.containerPort);
    setDeployEnv(p.env);
    checkDeployPort(p.hostPort);
  };

  const handleRunPreflight = async () => {
    if (!preflightInput.trim()) {
      warning('Please provide command, compose yaml, or ports to check.');
      return;
    }
    setPreflightChecking(true);
    setPreflightResult(null);
    try {
      const payload: any = {};
      if (preflightMode === 'command') {
        payload.command = preflightInput.trim();
      } else if (preflightMode === 'compose') {
        payload.compose_content = preflightInput.trim();
      } else {
        const ports = preflightInput
          .split(/[\s,]+/)
          .map((p) => parseInt(p.trim()))
          .filter((p) => !isNaN(p) && p > 0 && p <= 65535);
        if (ports.length === 0) {
          warning('Please enter valid port numbers.');
          setPreflightChecking(false);
          return;
        }
        payload.ports = ports;
      }
      const res = await api.checkPreflight(payload);
      setPreflightResult(res);
      if (res.has_collision) {
        warning(`Preflight detected ${res.collisions.length} port collision(s)!`);
      } else {
        success('Preflight passed! All requested ports are free.');
      }
    } catch (e: any) {
      error(`Preflight check failed: ${e.message}`);
    } finally {
      setPreflightChecking(false);
    }
  };

  const handleDeploySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!deployImage.trim() || !deployName.trim()) {
      warning('Container image and name are required.');
      return;
    }
    setDeploying(true);
    try {
      const envObj: Record<string, string> = {};
      deployEnv.split('\n').forEach(line => {
        const [k, ...v] = line.split('=');
        if (k && k.trim()) {
          envObj[k.trim()] = v.join('=').trim();
        }
      });
      await api.deployContainer({
        image: deployImage.trim(),
        name: deployName.trim(),
        ports: { [deployContainerPort]: deployHostPort },
        env: envObj,
        restart_policy: deployRestart,
      });
      success(`Container '${deployName}' deployed successfully!`);
      onAppAdded();
      onClose();
    } catch (e: any) {
      error(`Deployment failed: ${e.message}`);
    } finally {
      setDeploying(false);
    }
  };

  // Adopt from running host process
  const handleAdoptProcess = async (app: AppItem) => {
    setName(app.name);
    setPort(app.port);
    setActiveTab('custom');
    // cmdline/cwd are redacted from list summaries; fetch the admin detail view.
    try {
      const det = await api.getAppDetail(app.id);
      setWorkdir(det.app.cwd || '');
      setStartCmd(det.app.cmdline || '');
    } catch {
      setWorkdir('');
      setStartCmd('');
    }
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
      warning('Please enter an app name.');
      return;
    }
    if (startCmd.trim() || (stopCmd && stopCmd !== 'auto')) {
      warning('Custom commands run in a shell with Portly’s privileges — only use trusted commands.');
    }
    setSubmitting(true);
    try {
      let parsedHeaders: Record<string, string> = {};
      if (customHeaders.trim()) {
        try {
          parsedHeaders = JSON.parse(customHeaders);
        } catch {
          customHeaders.split('\n').forEach((line) => {
            const idx = line.indexOf(':');
            if (idx > 0) {
              const k = line.substring(0, idx).trim();
              const v = line.substring(idx + 1).trim();
              if (k) parsedHeaders[k] = v;
            }
          });
        }
      }

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
        expected_status: expectedStatus.trim() || '200,204,301,302',
        custom_headers: parsedHeaders,
      });

      // Override category and tags
      await api.patchApp(`custom:${customId}`, {
        category_id: categoryId,
        tags: tags.split(',').map((t) => t.trim()).filter(Boolean),
        pinned: pin,
      });

      success(`App '${name}' saved successfully!`);
      onAppAdded();
      onClose();
    } catch (err: any) {
      error(`Failed to add app: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleExternalSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!extName.trim() || !extUrl.trim()) {
      warning('Please enter both name and URL.');
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

      success(`External URL '${extName}' added!`);
      onAppAdded();
      onClose();
    } catch (err: any) {
      error(`Failed to add external URL: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleManualDockerSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualDockerName.trim()) {
      warning('Please enter container name.');
      return;
    }
    setName(manualDockerName.trim());
    setPort(manualDockerPort);
    setCategoryId('infrastructure');
    setTags('docker');
    setActiveTab('custom');
  };

  // Containers with published ports are already managed via their docker entry;
  // adopting them as custom apps would create a permanent false port conflict.
  const dockerApps = availableApps.filter((a) => a.source === 'docker' && !a.port);
  const containerRef = useFocusTrap<HTMLDivElement>(true, onClose);

  return (
    <div className="modal-backdrop" onClick={onClose} style={{ zIndex: 1200 }}>
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-app-title"
        className="modal-content"
        style={{
          width: '680px',
          maxWidth: '95vw',
          background: 'var(--surface-1)',
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
            <h2 id="add-app-title" className="c227" style={{ margin: 0, fontSize: '18px', fontWeight: 600, color: 'var(--text)' }}>Add Custom App</h2>
            <div className="c228" style={{ fontSize: '13px', color: 'var(--muted)', marginTop: '2px' }}>
              Track an app Portly can’t detect, adopt running services, or bookmark external web dashboards.
            </div>
          </div>
          <button type="button" className="c077" onClick={onClose} aria-label="Close"><Icon name="x" size={13} /></button>
        </div>

        {/* Tabs */}
        <div className="c093" style={{ marginBottom: '20px' }}>
          <button
            type="button"
            className={activeTab === 'custom' ? 'c094' : 'c095'}
            onClick={() => setActiveTab('custom')}
          >
            Custom App
          </button>
          <button
            type="button"
            className={activeTab === 'process' ? 'c094' : 'c095'}
            onClick={() => setActiveTab('process')}
          >
            From Process
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
          <button
            type="button"
            className={activeTab === 'deploy' ? 'c094' : 'c095'}
            onClick={() => setActiveTab('deploy')}
          >
            Deploy Container
          </button>
          <button
            type="button"
            className={activeTab === 'preflight' ? 'c094' : 'c095'}
            onClick={() => setActiveTab('preflight')}
          >
            <Icon name="bolt" size={13} /> Preflight Collision Check
          </button>
        </div>

        {/* Tab 1: From Host Process */}
        {activeTab === 'process' && (
          <div style={{ marginBottom: '20px', maxHeight: '320px', overflowY: 'auto' }}>
            <div style={{ fontSize: '13px', color: 'var(--muted)', marginBottom: '10px' }}>
              Select a running local process to adopt into Portly management:
            </div>
            {availableApps.filter((a) => a.source === 'host').length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', color: 'var(--muted)', fontSize: '13px' }}>
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
                    background: 'var(--surface-2)',
                    borderRadius: '8px',
                    marginBottom: '6px',
                  }}
                >
                  <div>
                    <span style={{ fontWeight: 600, color: 'var(--text)' }}>{h.name}</span>
                    <span style={{ fontFamily: 'JetBrains Mono, monospace', color: 'var(--accent)', marginLeft: '8px' }}>:{h.port}</span>
                    <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '2px' }}>
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
            <div style={{ fontSize: '13px', color: 'var(--muted)', marginBottom: '10px' }}>
              Discovered Docker containers without published ports — adopt them to add management commands:
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
                    background: 'var(--surface-2)',
                    borderRadius: '8px',
                    marginBottom: '6px',
                  }}
                >
                  <div>
                    <span style={{ fontWeight: 600, color: 'var(--text)' }}>{d.name}</span>
                    <span style={{ fontFamily: 'JetBrains Mono, monospace', color: 'var(--success)', marginLeft: '8px' }}>:{d.port}</span>
                    <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '2px' }}>
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
              <div style={{ padding: '20px', background: 'var(--surface-2)', borderRadius: '10px' }}>
                <p style={{ margin: '0 0 12px 0', fontSize: '13px', color: 'var(--warning)' }}>
                  No active Docker containers discovered on socket. You can specify a container manually:
                </p>
                <form onSubmit={handleManualDockerSubmit} style={{ display: 'flex', gap: '10px' }}>
                  <input
                    type="text"
                    name="manualDockerName"
                    aria-label="Container name"
                    autoComplete="off"
                    placeholder="Container Name (e.g. postgres-prod)"
                    value={manualDockerName}
                    onChange={(e) => setManualDockerName(e.target.value)}
                    className="c220"
                    style={{ flex: 2 }}
                    required
                  />
                  <input
                    type="number"
                    name="manualDockerPort"
                    aria-label="Port"
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
            <div style={{ fontSize: '13px', color: 'var(--muted)' }}>
              Add remote web dashboards, NAS portals, router admin pages, or cloud services to Portly:
            </div>
            <div>
              <label htmlFor="ext-name" style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>App / Dashboard Name</label>
              <input
                id="ext-name"
                name="extName"
                type="text"
                placeholder="e.g. Synology DSM or Proxmox VE"
                value={extName}
                onChange={(e) => setExtName(e.target.value)}
                autoComplete="off"
                className="c220"
                style={{ width: '100%', boxSizing: 'border-box' }}
                required
              />
            </div>
            <div>
              <label htmlFor="ext-url" style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>Full Target URL</label>
              <input
                id="ext-url"
                name="extUrl"
                type="url"
                placeholder="https://192.168.1.50:8006 or https://nas.local:5001"
                value={extUrl}
                onChange={(e) => setExtUrl(e.target.value)}
                autoComplete="off"
                className="c220"
                style={{ width: '100%', boxSizing: 'border-box' }}
                required
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              <div>
                <label htmlFor="ext-category" style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>Category</label>
                <select
                  id="ext-category"
                  name="extCategory"
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
                <label htmlFor="ext-tags" style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>Tags</label>
                <input
                  id="ext-tags"
                  name="extTags"
                  type="text"
                  value={extTags}
                  onChange={(e) => setExtTags(e.target.value)}
                  autoComplete="off"
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
              <button type="button" className="c078" onClick={onClose}>Cancel</button>
              <button type="submit" className="c080" disabled={submitting}>
                {submitting ? 'Saving…' : 'Add Bookmark'}
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
                <label htmlFor="custom-name" style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>Name</label>
                <input
                  id="custom-name"
                  name="customName"
                  type="text"
                  placeholder="Billing API"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  autoComplete="off"
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                  required
                />
              </div>
              <div>
                <span style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>Icon</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <div
                    className="c233"
                    style={{
                      width: '34px',
                      height: '34px',
                      borderRadius: '8px',
                      background: 'var(--accent)',
                      color: 'var(--bg)',
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
            <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', marginTop: '6px' }}>Network</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              <div>
                <label htmlFor="custom-host" style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>Host</label>
                <input
                  id="custom-host"
                  name="customHost"
                  type="text"
                  value={host}
                  onChange={(e) => setHost(e.target.value)}
                  autoComplete="off"
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
              <div>
                <label htmlFor="custom-port" style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>Port</label>
                <input
                  id="custom-port"
                  name="customPort"
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
              <div
                aria-live="polite"
                style={{ fontSize: '12px', color: portStatus.free ? 'var(--success)' : 'var(--danger)', display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <span style={{ display: 'inline-flex' }}><Icon name={portStatus.free ? 'check' : 'x'} size={13} color={portStatus.free ? 'var(--success)' : 'var(--danger)'} /></span>
                <span>
                  {portStatus.free
                    ? `Port ${port} is free · opens http://${host}:${port}`
                    : `Port ${port} is in use: ${portStatus.used_by}`}
                </span>
              </div>
            )}

            {/* Organize: Category & Tags */}
            <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', marginTop: '6px' }}>Organize</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              <div>
                <label htmlFor="custom-category" style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>Category</label>
                <select
                  id="custom-category"
                  name="customCategory"
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
                <label htmlFor="custom-tags" style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>Tags (comma-separated)</label>
                <input
                  id="custom-tags"
                  name="customTags"
                  type="text"
                  placeholder="internal, billing"
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                  autoComplete="off"
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
            </div>

            {/* Health Probing Settings */}
            <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', marginTop: '6px' }}>Health Checks & Probing</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 140px', gap: '14px' }}>
              <div>
                <label htmlFor="custom-health-path" style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>Health check path</label>
                <input
                  id="custom-health-path"
                  name="customHealthPath"
                  autoComplete="off"
                  type="text"
                  placeholder="/health or /"
                  value={healthPath}
                  onChange={(e) => setHealthPath(e.target.value)}
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
              <div>
                <label htmlFor="custom-health-interval" style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>Interval (sec)</label>
                <input
                  id="custom-health-interval"
                  name="customHealthInterval"
                  autoComplete="off"
                  type="number"
                  min={5}
                  max={3600}
                  value={healthInterval}
                  onChange={(e) => setHealthInterval(parseInt(e.target.value) || 30)}
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              <div>
                <label htmlFor="custom-expected-status" style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>Expected status codes (comma-separated)</label>
                <input
                  id="custom-expected-status"
                  name="customExpectedStatus"
                  autoComplete="off"
                  type="text"
                  placeholder="200,204,301,302"
                  value={expectedStatus}
                  onChange={(e) => setExpectedStatus(e.target.value)}
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
              <div>
                <label htmlFor="custom-headers" style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>Custom headers (JSON or KEY: VAL)</label>
                <input
                  id="custom-headers"
                  name="customHeaders"
                  autoComplete="off"
                  type="text"
                  placeholder='Authorization: Bearer token123'
                  value={customHeaders}
                  onChange={(e) => setCustomHeaders(e.target.value)}
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
            </div>

            {/* Run Controls */}
            <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', marginTop: '6px' }}>Run Controls</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              <div>
                <label htmlFor="custom-start-cmd" style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>Start command</label>
                <input
                  id="custom-start-cmd"
                  name="customStartCmd"
                  type="text"
                  placeholder="npm run start or python app.py"
                  value={startCmd}
                  onChange={(e) => setStartCmd(e.target.value)}
                  autoComplete="off"
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
              <div>
                <label htmlFor="custom-stop-cmd" style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>Stop command</label>
                <input
                  id="custom-stop-cmd"
                  name="customStopCmd"
                  type="text"
                  placeholder="auto (terminate process)"
                  value={stopCmd}
                  onChange={(e) => setStopCmd(e.target.value)}
                  autoComplete="off"
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              <div>
                <label htmlFor="custom-workdir" style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>Working directory</label>
                <input
                  id="custom-workdir"
                  name="customWorkdir"
                  type="text"
                  placeholder="/opt/my-app"
                  value={workdir}
                  onChange={(e) => setWorkdir(e.target.value)}
                  autoComplete="off"
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
              <div>
                <label htmlFor="custom-log-file" style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>Log file path</label>
                <input
                  id="custom-log-file"
                  name="customLogFile"
                  type="text"
                  placeholder="/var/log/my-app.log"
                  value={logFile}
                  onChange={(e) => setLogFile(e.target.value)}
                  autoComplete="off"
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
            </div>

            {/* Switches */}
            <div style={{ display: 'flex', gap: '20px', marginTop: '6px' }}>
              <label style={{ fontSize: '13px', color: 'var(--text)', display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  name="startOnBoot"
                  checked={startOnBoot}
                  onChange={(e) => setStartOnBoot(e.target.checked)}
                  className="c173"
                />
                Start on boot
              </label>
              <label style={{ fontSize: '13px', color: 'var(--text)', display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  name="pin"
                  checked={pin}
                  onChange={(e) => setPin(e.target.checked)}
                  className="c173"
                />
                Pin to favorites
              </label>
            </div>

            {/* Footer */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '14px', borderTop: '1px solid rgba(255,255,255,0.07)', paddingTop: '16px' }}>
              <span style={{ fontSize: '12px', color: 'var(--muted)' }}>Saved to your Portly SQLite store.</span>
              <div style={{ display: 'flex', gap: '10px' }}>
                <button type="button" className="c078" onClick={onClose}>Cancel</button>
                <button type="submit" className="c080" disabled={submitting}>
                  {submitting ? 'Adding…' : 'Add App'}
                </button>
              </div>
            </div>
          </form>
        )}

        {/* Tab 4: Deploy New Container */}
        {activeTab === 'deploy' && (
          <form onSubmit={handleDeploySubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ fontSize: '13px', color: 'var(--muted)' }}>
              Launch a new container directly from Docker registry with custom port bindings and automatic conflict checking:
            </div>

            {/* Quick Templates */}
            <div>
              <span style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '8px' }}>
                1-Click Quick Deploy Templates
              </span>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {PRESET_TEMPLATES.map((tmpl) => (
                  <button
                    key={tmpl.name}
                    type="button"
                    className="c078"
                    style={{ fontSize: '12px', padding: '4px 10px', height: '28px' }}
                    onClick={() => handleSelectPreset(tmpl)}
                  >
                    + {tmpl.label}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              <div>
                <label htmlFor="deploy-image" style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>
                  Image Tag (e.g. redis:7-alpine, postgres:16)
                </label>
                <input
                  id="deploy-image"
                  name="deploy_image"
                  autoComplete="off"
                  type="text"
                  required
                  placeholder="e.g. redis:7-alpine"
                  value={deployImage}
                  onChange={(e) => setDeployImage(e.target.value)}
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label htmlFor="deploy-name" style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>
                  Container Name
                </label>
                <input
                  id="deploy-name"
                  name="deploy_name"
                  autoComplete="off"
                  type="text"
                  required
                  placeholder="e.g. my-redis"
                  value={deployName}
                  onChange={(e) => setDeployName(e.target.value)}
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              <div>
                <label htmlFor="deploy-host-port" style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>
                  Host Port
                </label>
                <input
                  id="deploy-host-port"
                  name="deploy_host_port"
                  autoComplete="off"
                  type="number"
                  required
                  value={deployHostPort}
                  onChange={(e) => {
                    const p = parseInt(e.target.value) || 0;
                    setDeployHostPort(p);
                    checkDeployPort(p);
                  }}
                  className="c218"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
                {deployPortStatus && (
                  <div style={{ fontSize: '11px', marginTop: '4px', color: deployPortStatus.free ? 'var(--success)' : 'var(--danger)' }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}><Icon name={deployPortStatus.free ? 'check' : 'x'} size={13} /> {deployPortStatus.free ? 'Port is free to bind' : `Port conflict: ${deployPortStatus.used_by}`}</span>
                  </div>
                )}
              </div>

              <div>
                <label htmlFor="deploy-container-port" style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>
                  Container Port / Protocol
                </label>
                <input
                  id="deploy-container-port"
                  name="deploy_container_port"
                  autoComplete="off"
                  type="text"
                  required
                  placeholder="e.g. 80/tcp or 6379/tcp"
                  value={deployContainerPort}
                  onChange={(e) => setDeployContainerPort(e.target.value)}
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
            </div>

            <div>
              <label htmlFor="deploy-env" style={{ display: 'block', fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>
                Environment Variables (KEY=VALUE, one per line)
              </label>
              <textarea
                id="deploy-env"
                rows={3}
                placeholder="FOO=bar&#10;PORT=80"
                value={deployEnv}
                onChange={(e) => setDeployEnv(e.target.value)}
                className="c220"
                style={{ width: '100%', boxSizing: 'border-box', fontFamily: 'JetBrains Mono, monospace', fontSize: '12px' }}
              />
            </div>

            <div style={{ display: 'flex', gap: '12px', alignItems: 'center', justifyContent: 'flex-end', marginTop: '10px' }}>
              <button type="button" className="c078" onClick={onClose}>Cancel</button>
              <button
                type="submit"
                className="c080"
                disabled={deploying || (deployPortStatus !== null && !deployPortStatus.free)}
              >
                {deploying ? 'Deploying Container…' : 'Deploy Container'}
              </button>
            </div>
          </form>
        )}

        {/* Tab 5: Preflight Collision Check (D-10, F-5) */}
        {activeTab === 'preflight' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ fontSize: '13px', color: 'var(--muted)', lineHeight: 1.5 }}>
              Preflight checks validate whether ports declared in a <code style={{ color: 'var(--accent)' }}>docker run</code> command, a <code style={{ color: 'var(--accent)' }}>docker-compose.yml</code> file, or a list of ports are available before launching.
            </div>

            <div style={{ display: 'flex', gap: '10px' }}>
              {(['command', 'compose', 'ports'] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => {
                    setPreflightMode(m);
                    setPreflightResult(null);
                    if (m === 'command') setPreflightInput('docker run -d -p 8080:80 -p 5432:5432 postgres');
                    else if (m === 'compose') setPreflightInput('version: "3.8"\nservices:\n  web:\n    image: nginx\n    ports:\n      - "8080:80"\n  db:\n    image: redis\n    ports:\n      - "6379:6379"');
                    else setPreflightInput('3000, 5432, 6379, 8080');
                  }}
                  style={{
                    padding: '6px 12px',
                    borderRadius: '7px',
                    fontSize: '12px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    background: preflightMode === m ? 'var(--accent)' : 'rgba(255,255,255,0.06)',
                    color: preflightMode === m ? 'var(--on-accent)' : 'var(--text)',
                    border: 0,
                  }}
                >
                  {m === 'command' ? 'Docker Run Command' : m === 'compose' ? 'Docker Compose YAML' : 'Port List'}
                </button>
              ))}
            </div>

            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const file = e.dataTransfer.files[0];
                if (file) {
                  const reader = new FileReader();
                  reader.onload = (event) => {
                    const text = event.target?.result as string;
                    if (text) {
                      setPreflightMode('compose');
                      setPreflightInput(text);
                      success(`Loaded '${file.name}' into Preflight!`);
                    }
                  };
                  reader.readAsText(file);
                }
              }}
              style={{
                border: '1px dashed rgba(255,255,255,0.15)',
                borderRadius: '8px',
                padding: '10px 14px',
                background: 'rgba(255,255,255,0.02)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <label htmlFor="preflight-input" style={{ fontSize: '12px', color: 'var(--muted)' }}>
                  {preflightMode === 'command' ? 'Command Line Invocation' : preflightMode === 'compose' ? 'Compose YAML Definition (or drop .yml file here)' : 'Comma or Space-separated Ports'}
                </label>
                <span style={{ fontSize: '11px', color: 'var(--muted)' }}>Drag & drop .yml file supported</span>
              </div>
              <textarea
                id="preflight-input"
                rows={6}
                value={preflightInput}
                onChange={(e) => setPreflightInput(e.target.value)}
                className="c220"
                style={{ width: '100%', boxSizing: 'border-box', fontFamily: 'JetBrains Mono, monospace', fontSize: '12px' }}
                placeholder={preflightMode === 'command' ? 'docker run -p 8080:80 …' : 'services:\n  …'}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button
                type="button"
                className="c080"
                disabled={preflightChecking}
                onClick={handleRunPreflight}
                style={{ background: 'var(--accent)', color: 'var(--on-accent)' }}
              >
                {preflightChecking ? 'Checking Collisions…' : 'Run Preflight Check'}
              </button>
            </div>

            {/* Results */}
            {preflightResult && (
              <div
                style={{
                  background: 'var(--surface-1)',
                  borderRadius: '10px',
                  padding: '16px',
                  border: `1px solid ${preflightResult.has_collision ? 'rgba(255, 138, 138, 0.3)' : 'rgba(94, 234, 212, 0.3)'}`,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                  <span style={{ display: 'inline-flex' }}><Icon name={preflightResult.has_collision ? 'warning' : 'check'} size={18} color={preflightResult.has_collision ? 'var(--warning)' : 'var(--success)'} /></span>
                  <div style={{ fontSize: '14px', fontWeight: 600, color: preflightResult.has_collision ? 'var(--danger)' : 'var(--success)' }}>
                    {preflightResult.has_collision
                      ? `${preflightResult.collisions.length} Port Collision(s) Detected!`
                      : 'All Requested Ports Available!'}
                  </div>
                </div>

                {preflightResult.has_collision ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {preflightResult.collisions.map((col, idx) => {
                      const detail = preflightResult.details?.find((d) => d.requested_port === col.port);
                      const suggested = detail?.suggested_port;

                      return (
                        <div
                          key={idx}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            padding: '8px 12px',
                            background: 'var(--surface-input)',
                            borderRadius: '6px',
                            fontSize: '12px',
                            gap: '8px',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                            <span style={{ fontFamily: 'JetBrains Mono, monospace', color: 'var(--danger)', fontWeight: 600 }}>
                              Port {col.port}/{col.proto || 'tcp'}
                            </span>
                            <span style={{ color: 'var(--text)' }}>
                              Bound by: <strong style={{ color: 'var(--warning)' }}>{col.service_name || col.owner || 'Unknown Socket'}</strong>
                            </span>
                            <span style={{ color: 'var(--muted)', fontSize: '11px' }}>
                              Source: {col.source || 'host'}
                            </span>
                          </div>

                          {suggested && (
                            <button
                              type="button"
                              className="c078"
                              style={{ fontSize: '11px', padding: '2px 8px', color: 'var(--success)', borderColor: 'rgba(94, 234, 212, 0.3)', whiteSpace: 'nowrap' }}
                              title={`Replace port ${col.port} with free port ${suggested}`}
                              onClick={() => {
                                const oldP = String(col.port);
                                const newP = String(suggested);
                                const portRegex = new RegExp(`(^|[^0-9])${oldP}(?![0-9])`, 'g');
                                setPreflightInput((prev) => prev.replace(portRegex, `$1${newP}`));
                                success(`Remapped port ${oldP} -> ${newP}! Click Preflight to re-verify.`);
                              }}
                            >
                              Use Free :{suggested} →
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div style={{ fontSize: '12px', color: 'var(--muted)' }}>
                    Checked {preflightResult.checked_ports.length} port(s): {preflightResult.checked_ports.join(', ')}. No socket or container conflicts found.
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
