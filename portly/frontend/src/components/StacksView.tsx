import React, { useEffect, useState } from 'react';
import { api } from '../api';
import { ComposeStack, PreflightResponse } from '../types';
import { useToast } from './Toast';
import { ConfirmDialog } from './ConfirmDialog';
import { Icon } from './Icon';

interface StacksViewProps {
  safeMode: boolean;
}

export const StacksView: React.FC<StacksViewProps> = ({ safeMode }) => {
  const { success, error, warning } = useToast();
  const [stacks, setStacks] = useState<ComposeStack[]>([]);
  const [selectedStack, setSelectedStack] = useState<ComposeStack | null>(null);
  const [loading, setLoading] = useState(true);

  // Editor state
  const [isEditing, setIsEditing] = useState(false);
  const [stackName, setStackName] = useState('');
  const [stackYaml, setStackYaml] = useState('');
  const [saving, setSaving] = useState(false);

  // Preflight state
  const [preflightChecking, setPreflightChecking] = useState(false);
  const [preflightResult, setPreflightResult] = useState<PreflightResponse | null>(null);

  // Execution state
  const [executingAction, setExecutingAction] = useState<string | null>(null);
  const [executionOutput, setExecutionOutput] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showDownConfirm, setShowDownConfirm] = useState(false);

  useEffect(() => {
    loadStacks();
  }, []);

  const loadStacks = async () => {
    try {
      const data = await api.getComposeStacks();
      setStacks(data.stacks || []);
      if (!selectedStack && data.stacks && data.stacks.length > 0) {
        setSelectedStack(data.stacks[0]);
        setStackName(data.stacks[0].name);
        setStackYaml(data.stacks[0].compose_yaml);
      }
    } catch {
      // Ignored
    } finally {
      setLoading(false);
    }
  };

  const handleSelectStack = (stack: ComposeStack) => {
    setSelectedStack(stack);
    setStackName(stack.name);
    setStackYaml(stack.compose_yaml);
    setIsEditing(false);
    setPreflightResult(null);
    setExecutionOutput(null);
  };

  const handleNewStack = () => {
    setSelectedStack(null);
    setStackName('my-new-stack');
    setStackYaml(`version: '3.8'\nservices:\n  web:\n    image: nginx:alpine\n    ports:\n      - "8080:80"\n    restart: unless-stopped\n`);
    setIsEditing(true);
    setPreflightResult(null);
    setExecutionOutput(null);
  };

  const handleRunPreflight = async () => {
    if (!stackYaml.trim()) {
      warning('Please enter Compose YAML content.');
      return;
    }
    setPreflightChecking(true);
    try {
      const res = await api.checkPreflight({ compose_content: stackYaml });
      setPreflightResult(res);
      if (res.has_collision) {
        warning(`Preflight detected ${res.collisions.length} collision(s)!`);
      } else {
        success('Preflight passed! All ports are free to bind.');
      }
    } catch (err: any) {
      error(`Preflight check failed: ${err.message}`);
    } finally {
      setPreflightChecking(false);
    }
  };

  const handleSaveStack = async (force: boolean = false) => {
    if (!stackName.trim() || !stackYaml.trim()) {
      warning('Stack name and YAML content are required.');
      return;
    }
    setSaving(true);
    try {
      await api.saveComposeStack({
        name: stackName.trim(),
        compose_yaml: stackYaml,
        force,
      });
      success(`Stack '${stackName}' saved!`);
      setIsEditing(false);
      loadStacks();
    } catch (err: any) {
      if (err.code === 'PORT_COLLISION' && !force) {
        warning(`Cannot save stack: port collision detected. Review preflight check.`);
        if (err.preflight) setPreflightResult(err.preflight);
      } else {
        error(`Failed to save stack: ${err.message}`);
      }
    } finally {
      setSaving(false);
    }
  };

  const handleStackAction = async (action: 'up' | 'down' | 'restart' | 'stop') => {
    if (!selectedStack) return;
    if (safeMode) {
      warning('Safe mode is ON. Unlock safe mode in the sidebar to control stacks.');
      return;
    }
    setExecutingAction(action);
    setExecutionOutput('Executing docker compose…');
    try {
      const res = await api.executeStackAction(selectedStack.name, action);
      if (res.status === 'success') {
        success(res.message);
      } else {
        error(res.message);
      }
      setExecutionOutput(res.output || res.message || 'Operation finished.');
      loadStacks();
    } catch (err: any) {
      error(`Stack action failed: ${err.message}`);
      setExecutionOutput(`Error: ${err.message}`);
    } finally {
      setExecutingAction(null);
    }
  };

  const confirmDeleteStack = async () => {
    if (!selectedStack) return;
    setShowDeleteConfirm(false);
    try {
      await api.deleteComposeStack(selectedStack.name);
      success(`Stack '${selectedStack.name}' deleted.`);
      setSelectedStack(null);
      loadStacks();
    } catch (err: any) {
      error(`Failed to delete stack: ${err.message}`);
    }
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: '20px', height: 'calc(100vh - 180px)', minHeight: '600px' }}>
      {/* Left: Stacks Directory Panel */}
      <div
        style={{
          background: 'var(--surface-1)',
          border: '1px solid rgba(255,255,255,0.07)',
          borderRadius: '14px',
          padding: '18px',
          display: 'flex',
          flexDirection: 'column',
          gap: '14px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '12px' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--text)' }}>Compose Stacks</h2>
            <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '2px' }}>{stacks.length} managed stack(s)</div>
          </div>
          <button
            type="button"
            className="c080"
            style={{ fontSize: '12px', padding: '4px 10px' }}
            onClick={handleNewStack}
          >
            + New
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', overflowY: 'auto', flex: 1 }}>
          {loading ? (
            <div style={{ color: 'var(--muted)', textAlign: 'center', padding: '20px 0', fontSize: '12px' }}>Loading stacks…</div>
          ) : stacks.length === 0 ? (
            <div style={{ color: 'var(--muted)', textAlign: 'center', padding: '30px 10px', fontSize: '12px' }}>
              No compose stacks yet. Click <strong>+ New</strong> to create your first multi-container stack.
            </div>
          ) : (
            stacks.map((s) => {
              const isSelected = selectedStack?.name === s.name;
              return (
                <div
                  key={s.name}
                  role="button"
                  tabIndex={0}
                  aria-label={`Select stack ${s.name}`}
                  onClick={() => handleSelectStack(s)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      handleSelectStack(s);
                    }
                  }}
                  style={{
                    padding: '12px',
                    borderRadius: '8px',
                    background: isSelected ? 'rgba(140, 158, 255, 0.12)' : 'var(--surface-2)',
                    border: isSelected ? '1px solid var(--accent)' : '1px solid rgba(255,255,255,0.06)',
                    cursor: 'pointer',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '4px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text)' }}>{s.name}</span>
                    <span
                      style={{
                        width: '8px',
                        height: '8px',
                        borderRadius: '50%',
                        background: s.status === 'running' ? 'var(--success)' : '#64748B',
                      }}
                      title={s.status}
                    />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--muted)' }}>
                    <span>{s.containers_running} container(s)</span>
                    <span>{s.ports.length > 0 ? `:${s.ports.join(', :')}` : 'No ports'}</span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Right: Stack Details & Editor Panel */}
      <div
        style={{
          background: 'var(--surface-1)',
          border: '1px solid rgba(255,255,255,0.07)',
          borderRadius: '14px',
          padding: '24px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
          overflowY: 'auto',
        }}
      >
        {selectedStack || isEditing ? (
          <>
            {/* Header / Actions toolbar */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.07)', paddingBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                {isEditing ? (
                  <input
                    type="text"
                    name="stack_name"
                    autoComplete="off"
                    value={stackName}
                    onChange={(e) => setStackName(e.target.value)}
                    placeholder="Stack Name"
                    className="c220"
                    style={{ fontSize: '16px', fontWeight: 600, width: '220px' }}
                  />
                ) : (
                  <div>
                    <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 600, color: 'var(--text)' }}>{selectedStack?.name}</h2>
                    <div style={{ fontSize: '12px', color: 'var(--muted)', marginTop: '2px' }}>
                      Status: <strong style={{ color: selectedStack?.status === 'running' ? 'var(--success)' : 'var(--muted)' }}>{selectedStack?.status.toUpperCase()}</strong>
                    </div>
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                {isEditing ? (
                  <>
                    <button
                      type="button"
                      className="c078"
                      disabled={preflightChecking}
                      onClick={handleRunPreflight}
                    >
                      {preflightChecking ? 'Validating…' : 'Preflight Validate'}
                    </button>
                    <button
                      type="button"
                      className="c080"
                      disabled={saving}
                      onClick={() => handleSaveStack(false)}
                    >
                      {saving ? 'Saving…' : 'Save Stack'}
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      className="c078"
                      onClick={() => setIsEditing(true)}
                    >
                      Edit YAML
                    </button>
                    <button
                      type="button"
                      className="c078"
                      disabled={executingAction !== null}
                      onClick={() => handleStackAction('up')}
                      style={{ color: 'var(--success)', borderColor: 'rgba(94, 234, 212, 0.3)' }}
                    >
                      {executingAction === 'up' ? 'Deploying…' : 'Deploy (Up -d)'}
                    </button>
                    <button
                      type="button"
                      className="c078"
                      disabled={executingAction !== null}
                      onClick={() => handleStackAction('restart')}
                    >
                      Restart
                    </button>
                    <button
                      type="button"
                      className="c078"
                      disabled={executingAction !== null}
                      onClick={() => {
                        // Safe mode stays gated by handleStackAction's own warning.
                        if (safeMode) { handleStackAction('down'); return; }
                        setShowDownConfirm(true);
                      }}
                      style={{ color: 'var(--danger)', borderColor: 'rgba(255, 138, 138, 0.3)' }}
                    >
                      Down
                    </button>
                    <button
                      type="button"
                      className="c077"
                      title="Delete Stack"
                      onClick={() => setShowDeleteConfirm(true)}
                    >
                      🗑
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Preflight Result Banner */}
            {preflightResult && (
              <div
                style={{
                  background: preflightResult.has_collision ? 'rgba(255,92,92,0.1)' : 'rgba(94,234,212,0.1)',
                  border: `1px solid ${preflightResult.has_collision ? 'rgba(255,92,92,0.3)' : 'rgba(94,234,212,0.3)'}`,
                  borderRadius: '8px',
                  padding: '12px 16px',
                  fontSize: '12.5px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <div>
                  <span style={{ fontWeight: 600, color: preflightResult.has_collision ? 'var(--danger)' : 'var(--success)' }}>
                    {preflightResult.has_collision
                      ? <><Icon name="warning" size={13} color="var(--danger)" /> {preflightResult.collisions.length} Port Collision(s) Detected:</>
                      : <><Icon name="check" size={13} color="var(--success)" /> All Declared Ports Available!</>}
                  </span>
                  {preflightResult.has_collision && (
                    <div style={{ marginTop: '4px', color: 'var(--text)', fontSize: '11.5px' }}>
                      {preflightResult.collisions.map((c) => `Port :${c.port} (${c.conflict_with})`).join(' · ')}
                    </div>
                  )}
                </div>
                {preflightResult.has_collision && isEditing && (
                  <button
                    type="button"
                    className="c078"
                    style={{ fontSize: '11px', padding: '3px 8px' }}
                    onClick={() => handleSaveStack(true)}
                  >
                    Force Save Anyway
                  </button>
                )}
              </div>
            )}

            {/* YAML Editor Area */}
            <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: '300px' }}>
              <div style={{ fontSize: '12px', color: 'var(--muted)', marginBottom: '6px' }}>docker-compose.yml definition:</div>
              <textarea
                value={stackYaml}
                onChange={(e) => setStackYaml(e.target.value)}
                readOnly={!isEditing}
                rows={14}
                className="c220"
                style={{
                  width: '100%',
                  flex: 1,
                  boxSizing: 'border-box',
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: '12.5px',
                  lineHeight: 1.6,
                  background: isEditing ? 'var(--surface-2)' : '#0B0D13',
                  color: isEditing ? 'var(--text)' : '#A0AEC0',
                }}
              />
            </div>

            {/* Terminal Output Log Area */}
            {executionOutput && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '12px', color: 'var(--muted)', fontWeight: 600 }}>Execution Terminal Output:</span>
                  <button type="button" className="c077" onClick={() => setExecutionOutput(null)} style={{ fontSize: '11px' }}><Icon name="x" size={11} /> Clear</button>
                </div>
                <div
                  style={{
                    background: '#06080B',
                    border: '1px solid rgba(255,255,255,0.08)',
                    borderRadius: '8px',
                    padding: '12px',
                    fontFamily: 'JetBrains Mono, monospace',
                    fontSize: '11.5px',
                    maxHeight: '180px',
                    overflowY: 'auto',
                    whiteSpace: 'pre-wrap',
                    color: 'var(--success)',
                  }}
                >
                  {executionOutput}
                </div>
              </div>
            )}
          </>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--muted)', fontSize: '14px' }}>
            Select a stack from the left panel or click <strong>+ New</strong> to start.
          </div>
        )}
      </div>

      {/* Down Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showDownConfirm}
        title={`Stop & Remove Stack '${selectedStack?.name}'?`}
        message={`Are you sure you want to run down on stack '${selectedStack?.name}'? All containers in this stack will be stopped and removed.`}
        confirmLabel="Run Compose Down"
        isDanger={true}
        onConfirm={() => {
          setShowDownConfirm(false);
          handleStackAction('down');
        }}
        onCancel={() => setShowDownConfirm(false)}
      />

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showDeleteConfirm}
        title={`Delete Stack '${selectedStack?.name}'`}
        message={`Are you sure you want to remove the Compose definition for '${selectedStack?.name}'? Running containers must be stopped first.`}
        confirmLabel="Delete Stack"
        isDanger={true}
        onConfirm={confirmDeleteStack}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </div>
  );
};