import React, { useState, useEffect } from 'react';
import { api } from '../api';
import { Category, Rule } from '../types';

interface CustomizeDrawerProps {
  onClose: () => void;
  viewType: 'table' | 'grid' | 'list' | 'board';
  onChangeViewType: (vt: 'table' | 'grid' | 'list' | 'board') => void;
  density: 'compact' | 'comfy';
  onChangeDensity: (d: 'compact' | 'comfy') => void;
  groupBy: string;
  onChangeGroupBy: (g: string) => void;
  sortBy: string;
  onChangeSortBy: (s: string) => void;
  categories: Category[];
  rules: Rule[];
  onRulesUpdated: () => void;
  accent: string;
  onChangeAccent: (color: string) => void;
  visibleFields: Record<string, boolean>;
  onToggleField: (field: string) => void;
}

export const CustomizeDrawer: React.FC<CustomizeDrawerProps> = ({
  onClose,
  viewType,
  onChangeViewType,
  density,
  onChangeDensity,
  groupBy,
  onChangeGroupBy,
  sortBy,
  onChangeSortBy,
  categories,
  rules,
  onRulesUpdated,
  accent,
  onChangeAccent,
  visibleFields,
  onToggleField,
}) => {
  const [showAddRule, setShowAddRule] = useState(false);
  const [newRuleField, setNewRuleField] = useState('image');
  const [newRuleOp, setNewRuleOp] = useState('contains');
  const [newRuleVal, setNewRuleVal] = useState('');
  const [newRuleCat, setNewRuleCat] = useState('development');

  // Webhook settings state
  const [webhookEnabled, setWebhookEnabled] = useState(false);
  const [webhookUrl, setWebhookUrl] = useState('');
  const [webhookType, setWebhookType] = useState('generic');
  const [webhookEvents, setWebhookEvents] = useState('port_opened,port_closed,container_state,port_conflict');
  const [testingWebhook, setTestingWebhook] = useState(false);
  const [webhookFeedback, setWebhookFeedback] = useState<string | null>(null);

  useEffect(() => {
    api.getSettings().then((s) => {
      if (s.webhook_enabled !== undefined) setWebhookEnabled(s.webhook_enabled.toLowerCase() === 'true');
      if (s.webhook_url) setWebhookUrl(s.webhook_url);
      if (s.webhook_type) setWebhookType(s.webhook_type);
      if (s.webhook_events) setWebhookEvents(s.webhook_events);
    }).catch(() => {});
  }, []);

  const handleSaveWebhook = async () => {
    try {
      await api.updateSettings({
        webhook_enabled: String(webhookEnabled),
        webhook_url: webhookUrl,
        webhook_type: webhookType,
        webhook_events: webhookEvents,
      });
      setWebhookFeedback('Webhook settings saved successfully!');
      setTimeout(() => setWebhookFeedback(null), 3500);
    } catch (e: any) {
      setWebhookFeedback(`Save error: ${e.message}`);
    }
  };

  const handleTestWebhook = async () => {
    if (!webhookUrl) {
      setWebhookFeedback('Please enter a Webhook URL first.');
      return;
    }
    setTestingWebhook(true);
    try {
      const res = await api.testWebhook({ url: webhookUrl, type: webhookType });
      setWebhookFeedback(`Test sent successfully: ${res.message}`);
    } catch (e: any) {
      setWebhookFeedback(`Test failed: ${e.message}`);
    } finally {
      setTestingWebhook(false);
      setTimeout(() => setWebhookFeedback(null), 4500);
    }
  };

  const accents = ['#8C9EFF', '#5EEAD4', '#FBBF77', '#F5A3D0', '#B6E36B', '#C4B5FD'];

  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newRuleVal.trim()) return;
    try {
      await api.saveRule({
        category_id: newRuleCat,
        field: newRuleField,
        operator: newRuleOp,
        value: newRuleVal.trim(),
        priority: 10,
      });
      setShowAddRule(false);
      setNewRuleVal('');
      onRulesUpdated();
    } catch (err: any) {
      alert(`Error saving rule: ${err.message}`);
    }
  };

  const handleDeleteRule = async (ruleId: string) => {
    try {
      await api.deleteRule(ruleId);
      onRulesUpdated();
    } catch {}
  };

  return (
    <div className="drawer-backdrop" onClick={onClose} style={{ zIndex: 1250 }}>
      <div
        className="drawer-panel"
        style={{
          width: '420px',
          background: '#101218',
          borderLeft: '1px solid rgba(255,255,255,0.08)',
          padding: '24px',
          display: 'flex',
          flexDirection: 'column',
          gap: '24px',
          boxSizing: 'border-box',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.07)', paddingBottom: '14px' }}>
          <span style={{ fontSize: '18px', fontWeight: 600, color: '#ECEEF3' }}>Customize Dashboard</span>
          <button type="button" className="c077" onClick={onClose} aria-label="Close drawer">✕</button>
        </div>

        {/* Layout */}
        <div className="c168">
          <div className="c169" style={{ fontSize: '12px', color: '#8D95A5', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '8px' }}>
            Layout View
          </div>
          <div className="c093" style={{ marginBottom: '10px' }}>
            {(['table', 'grid', 'list', 'board'] as const).map((vt) => (
              <button
                key={vt}
                type="button"
                className={viewType === vt ? 'c094' : 'c095'}
                onClick={() => onChangeViewType(vt)}
                style={{ textTransform: 'capitalize' }}
              >
                {vt}
              </button>
            ))}
          </div>

          <div className="c093">
            <button
              type="button"
              className={density === 'compact' ? 'c094' : 'c095'}
              onClick={() => onChangeDensity('compact')}
            >
              Compact
            </button>
            <button
              type="button"
              className={density === 'comfy' ? 'c094' : 'c095'}
              onClick={() => onChangeDensity('comfy')}
            >
              Comfy
            </button>
          </div>
        </div>

        {/* Organize */}
        <div className="c168">
          <div className="c169" style={{ fontSize: '12px', color: '#8D95A5', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '8px' }}>
            Organize & Sort
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '4px' }}>Group by</label>
              <select
                value={groupBy}
                onChange={(e) => onChangeGroupBy(e.target.value)}
                className="c215"
                style={{ width: '100%' }}
              >
                <option value="none">None</option>
                <option value="category">Category</option>
                <option value="source">Source</option>
                <option value="status">Status</option>
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '4px' }}>Sort by</label>
              <select
                value={sortBy}
                onChange={(e) => onChangeSortBy(e.target.value)}
                className="c215"
                style={{ width: '100%' }}
              >
                <option value="port">Port (Low to High)</option>
                <option value="name">Name</option>
                <option value="cpu">CPU %</option>
                <option value="ram">RAM</option>
                <option value="uptime">Uptime</option>
              </select>
            </div>
          </div>
        </div>

        {/* Card & Column Fields */}
        <div className="c168">
          <div className="c169" style={{ fontSize: '12px', color: '#8D95A5', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '8px' }}>
            Card & Column Fields
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {[
              { id: 'port', label: 'Port number' },
              { id: 'source', label: 'Source tag (Local / Docker)' },
              { id: 'cpuram', label: 'CPU and RAM stats' },
              { id: 'bind', label: 'Bind address' },
              { id: 'uptime', label: 'Uptime duration' },
            ].map((f) => (
              <label key={f.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '13px', color: '#ECEEF3', cursor: 'pointer' }}>
                <span>{f.label}</span>
                <input
                  type="checkbox"
                  checked={visibleFields[f.id] !== false}
                  onChange={() => onToggleField(f.id)}
                  className="c173"
                />
              </label>
            ))}
          </div>
        </div>

        {/* Accent Color */}
        <div className="c168">
          <div className="c169" style={{ fontSize: '12px', color: '#8D95A5', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '8px' }}>
            Accent Color
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            {accents.map((col) => (
              <button
                key={col}
                type="button"
                aria-label={`Color ${col}`}
                onClick={() => onChangeAccent(col)}
                style={{
                  width: '28px',
                  height: '28px',
                  borderRadius: '50%',
                  backgroundColor: col,
                  border: accent === col ? '2px solid #FFFFFF' : '2px solid transparent',
                  cursor: 'pointer',
                  outline: 'none',
                }}
              />
            ))}
          </div>
        </div>

        {/* Auto-categorize Rules */}
        <div className="c168">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <div className="c169" style={{ fontSize: '12px', color: '#8D95A5', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Auto-categorize Rules
            </div>
            <button
              type="button"
              className="c078"
              style={{ height: '24px', fontSize: '11px', padding: '0 8px' }}
              onClick={() => setShowAddRule(true)}
            >
              + Add Rule
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '200px', overflowY: 'auto' }}>
            {rules.map((r) => {
              const cat = categories.find((c) => c.id === r.category_id);
              return (
                <div
                  key={r.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '6px 10px',
                    background: '#151821',
                    borderRadius: '6px',
                    fontSize: '12px',
                  }}
                >
                  <span style={{ color: '#ECEEF3', fontFamily: 'JetBrains Mono, monospace' }}>
                    {r.field} {r.operator} {r.value}
                  </span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ color: cat?.color || '#8C9EFF', fontWeight: 600 }}>
                      → {cat?.name || r.category_id}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleDeleteRule(r.id)}
                      style={{ background: 'none', border: 0, color: '#8D95A5', cursor: 'pointer', padding: 0 }}
                      title="Delete rule"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Add rule sub-dialog */}
        {showAddRule && (
          <form onSubmit={handleCreateRule} style={{ background: '#151821', padding: '14px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.08)' }}>
            <div style={{ fontSize: '13px', fontWeight: 600, color: '#ECEEF3', marginBottom: '10px' }}>Create Rule</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '8px' }}>
              <select value={newRuleField} onChange={(e) => setNewRuleField(e.target.value)} className="c215">
                <option value="image">Image name</option>
                <option value="process">Process name</option>
                <option value="port">Port range</option>
                <option value="compose_project">Compose project</option>
              </select>
              <select value={newRuleOp} onChange={(e) => setNewRuleOp(e.target.value)} className="c215">
                <option value="contains">Contains</option>
                <option value="equals">Equals</option>
                <option value="range">Range (e.g. 3000-3999)</option>
                <option value="startswith">Starts with</option>
              </select>
            </div>
            <input
              type="text"
              placeholder="Match value (e.g. postgres, 3000-3999)"
              value={newRuleVal}
              onChange={(e) => setNewRuleVal(e.target.value)}
              className="c220"
              style={{ width: '100%', marginBottom: '8px', boxSizing: 'border-box' }}
              required
            />
            <div style={{ marginBottom: '10px' }}>
              <label style={{ display: 'block', fontSize: '11px', color: '#8D95A5', marginBottom: '4px' }}>Assign Category</label>
              <select value={newRuleCat} onChange={(e) => setNewRuleCat(e.target.value)} className="c215" style={{ width: '100%' }}>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button type="button" className="c078" onClick={() => setShowAddRule(false)}>Cancel</button>
              <button type="submit" className="c080">Save Rule</button>
            </div>
          </form>
        )}

        {/* Webhooks & Alerts */}
        <div className="c168" style={{ borderTop: '1px solid rgba(255,255,255,0.07)', paddingTop: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
            <div className="c169" style={{ fontSize: '12px', color: '#8D95A5', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Webhooks & Alerting
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#ECEEF3', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={webhookEnabled}
                onChange={(e) => setWebhookEnabled(e.target.checked)}
              />
              Enabled
            </label>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '11px', color: '#8D95A5', marginBottom: '4px' }}>Webhook Type</label>
              <select
                value={webhookType}
                onChange={(e) => setWebhookType(e.target.value)}
                className="c215"
                style={{ width: '100%' }}
              >
                <option value="generic">Generic JSON / Ntfy / Gotify</option>
                <option value="discord">Discord Webhook</option>
                <option value="slack">Slack Incoming Webhook</option>
                <option value="telegram">Telegram Bot</option>
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '11px', color: '#8D95A5', marginBottom: '4px' }}>Endpoint URL</label>
              <input
                type="text"
                placeholder={webhookType === 'discord' ? 'https://discord.com/api/webhooks/...' : 'https://ntfy.sh/my-portly-alerts'}
                value={webhookUrl}
                onChange={(e) => setWebhookUrl(e.target.value)}
                className="c220"
                style={{ width: '100%', boxSizing: 'border-box', fontSize: '12px' }}
              />
            </div>

            {webhookFeedback && (
              <div style={{ fontSize: '12px', padding: '6px 10px', borderRadius: '6px', background: 'rgba(140, 158, 255, 0.15)', color: '#8C9EFF' }}>
                {webhookFeedback}
              </div>
            )}

            <div style={{ display: 'flex', gap: '8px', marginTop: '4px' }}>
              <button
                type="button"
                className="c078"
                style={{ flex: 1, fontSize: '12px' }}
                onClick={handleTestWebhook}
                disabled={testingWebhook}
              >
                {testingWebhook ? 'Sending...' : 'Test Alert'}
              </button>
              <button
                type="button"
                className="c080"
                style={{ flex: 1, fontSize: '12px' }}
                onClick={handleSaveWebhook}
              >
                Save Alerts
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
