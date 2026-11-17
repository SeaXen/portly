import React, { useEffect, useState } from 'react';
import { api } from '../api';
import { AppItem, ConflictItem, PortReservation } from '../types';
import { useToast } from './Toast';

interface ConflictsViewProps {
  conflicts: ConflictItem[];
  apps: AppItem[];
  onOpenDetail: (app: AppItem) => void;
  onSelectNav: (nav: string) => void;
}

export const ConflictsView: React.FC<ConflictsViewProps> = ({
  conflicts,
  apps,
  onOpenDetail,
  onSelectNav,
}) => {
  const { success, error } = useToast();
  const [reservations, setReservations] = useState<PortReservation[]>([]);
  const [loadingRes, setLoadingRes] = useState(false);
  const [showAddRes, setShowAddRes] = useState(false);
  const [resPort, setResPort] = useState(8080);
  const [resProto, setResProto] = useState('tcp');
  const [resName, setResName] = useState('');
  const [resService, setResService] = useState('');
  const [resDesc, setResDesc] = useState('');
  const [submittingRes, setSubmittingRes] = useState(false);

  useEffect(() => {
    loadReservations();
  }, []);

  const loadReservations = async () => {
    setLoadingRes(true);
    try {
      const data = await api.getPortReservations();
      setReservations(data.reservations || []);
    } catch {
      // Ignored if unauthenticated or error
    } finally {
      setLoadingRes(false);
    }
  };

  const handleCreateReservation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resName.trim() || !resPort) return;
    setSubmittingRes(true);
    try {
      await api.createPortReservation({
        port: resPort,
        proto: resProto,
        name: resName.trim(),
        service: resService.trim() || undefined,
        description: resDesc.trim() || undefined,
      });
      success(`Port ${resPort}/${resProto} reserved for '${resName}'!`);
      setShowAddRes(false);
      setResName('');
      setResService('');
      setResDesc('');
      loadReservations();
    } catch (err: any) {
      error(`Failed to reserve port: ${err.message}`);
    } finally {
      setSubmittingRes(false);
    }
  };

  const handleDeleteReservation = async (id: string, name: string) => {
    try {
      await api.deletePortReservation(id);
      success(`Reservation for '${name}' deleted.`);
      loadReservations();
    } catch (err: any) {
      error(`Failed to delete reservation: ${err.message}`);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', width: '100%', boxSizing: 'border-box' }}>
      {/* Port Conflicts Section */}
      <div style={{ background: '#101218', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '14px', padding: '24px' }}>
        <div style={{ marginBottom: '20px' }}>
          <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 600, color: '#ECEEF3' }}>Port Conflicts & Collisions</h2>
          <div style={{ fontSize: '13px', color: '#8D95A5', marginTop: '4px' }}>
            Conflicts occur when two different processes or containers attempt to bind to the same host port.
          </div>
        </div>

        {conflicts.length === 0 ? (
          <div style={{ padding: '40px 24px', textAlign: 'center' }}>
            <div style={{ fontSize: '36px', marginBottom: '10px' }}>✓</div>
            <div style={{ fontSize: '15px', fontWeight: 600, color: '#5EEAD4', marginBottom: '6px' }}>No Active Port Collisions</div>
            <div style={{ fontSize: '13px', color: '#8D95A5', maxWidth: '420px', margin: '0 auto 16px auto' }}>
              Every active listener on your system has a unique, uncontested port assignment.
            </div>
            <button type="button" className="c078" onClick={() => onSelectNav('ports')}>
              View All Ports →
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {conflicts.map((c, i) => {
              const collidingApps = apps.filter((a) => a.port === c.port);

              return (
                <div
                  key={i}
                  style={{
                    background: '#151821',
                    border: '1px solid rgba(255, 138, 138, 0.25)',
                    borderRadius: '12px',
                    padding: '18px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#FF8A8A' }} />
                      <span style={{ fontSize: '15px', fontWeight: 700, color: '#FF8A8A' }}>
                        Port Conflict on :{c.port}
                      </span>
                    </div>
                    <span style={{ fontSize: '12px', color: '#8D95A5' }}>
                      {collidingApps.length} competing services
                    </span>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
                    {collidingApps.map((app) => (
                      <div
                        key={app.id}
                        style={{
                          background: '#101218',
                          border: '1px solid rgba(255,255,255,0.06)',
                          borderRadius: '10px',
                          padding: '14px',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                        }}
                      >
                        <div>
                          <div style={{ fontWeight: 600, color: '#ECEEF3' }}>{app.name}</div>
                          <div style={{ fontSize: '12px', color: '#8D95A5', marginTop: '2px' }}>
                            {app.source === 'docker' ? app.image : (app.process_name ? `${app.process_name}${app.pid ? ` (PID ${app.pid})` : ''}` : 'Host')}
                          </div>
                        </div>

                        <button
                          type="button"
                          className="c080"
                          style={{ height: '30px', fontSize: '12px', padding: '0 10px' }}
                          onClick={() => onOpenDetail(app)}
                        >
                          Change Port
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Port Reservations & Intent Registry Section */}
      <div style={{ background: '#101218', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '14px', padding: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '18px' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 600, color: '#ECEEF3' }}>Port Reservations & Intent Registry</h2>
            <div style={{ fontSize: '13px', color: '#8D95A5', marginTop: '4px' }}>
              Reserve ports for planned databases or stacks. Portly alerts if unexpected listeners bind to them and warns during preflight checks.
            </div>
          </div>
          <button
            type="button"
            className="c080"
            style={{ fontSize: '13px', padding: '6px 14px' }}
            onClick={() => setShowAddRes(!showAddRes)}
          >
            {showAddRes ? '✕ Close Form' : '+ New Reservation'}
          </button>
        </div>

        {/* Add Reservation Form */}
        {showAddRes && (
          <form
            onSubmit={handleCreateReservation}
            style={{
              background: '#151821',
              border: '1px solid rgba(140, 158, 255, 0.25)',
              borderRadius: '12px',
              padding: '18px',
              marginBottom: '20px',
              display: 'flex',
              flexDirection: 'column',
              gap: '14px',
            }}
          >
            <div style={{ fontWeight: 600, color: '#8C9EFF', fontSize: '14px' }}>Create Port Reservation</div>
            <div style={{ display: 'grid', gridTemplateColumns: '120px 100px 1fr', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '4px' }}>Port</label>
                <input
                  type="number"
                  required
                  min={1}
                  max={65535}
                  value={resPort}
                  onChange={(e) => setResPort(parseInt(e.target.value) || 0)}
                  className="c218"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '4px' }}>Protocol</label>
                <select
                  value={resProto}
                  onChange={(e) => setResProto(e.target.value)}
                  className="c215"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                >
                  <option value="tcp">TCP</option>
                  <option value="udp">UDP</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '4px' }}>Reservation Name</label>
                <input
                  type="text"
                  name="reservation_name"
                  autoComplete="off"
                  required
                  placeholder="e.g. Staging PostgreSQL or Ollama LLM"
                  value={resName}
                  onChange={(e) => setResName(e.target.value)}
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '4px' }}>Target Service (optional)</label>
                <input
                  type="text"
                  name="target_service"
                  autoComplete="off"
                  placeholder="e.g. postgres-staging"
                  value={resService}
                  onChange={(e) => setResService(e.target.value)}
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#8D95A5', marginBottom: '4px' }}>Notes / Description</label>
                <input
                  type="text"
                  name="reservation_description"
                  autoComplete="off"
                  placeholder="e.g. Reserved for Q4 analytics cluster"
                  value={resDesc}
                  onChange={(e) => setResDesc(e.target.value)}
                  className="c220"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                />
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '6px' }}>
              <button type="button" className="c078" onClick={() => setShowAddRes(false)}>Cancel</button>
              <button type="submit" className="c080" disabled={submittingRes}>
                {submittingRes ? 'Saving…' : 'Save Reservation'}
              </button>
            </div>
          </form>
        )}

        {/* Reservations List */}
        {reservations.length === 0 ? (
          <div style={{ padding: '30px', textAlign: 'center', color: '#8D95A5', fontSize: '13px' }}>
            No port reservations defined. Click <strong>+ New Reservation</strong> to claim ports for planned workloads.
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '12px' }}>
            {reservations.map((r) => (
              <div
                key={r.id}
                style={{
                  background: '#151821',
                  border: r.is_colliding ? '1px solid rgba(255, 138, 138, 0.4)' : '1px solid rgba(255,255,255,0.08)',
                  borderRadius: '10px',
                  padding: '14px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span
                      style={{
                        fontFamily: 'JetBrains Mono, monospace',
                        fontSize: '13px',
                        fontWeight: 700,
                        padding: '2px 8px',
                        borderRadius: '6px',
                        background: r.is_colliding ? 'rgba(255, 138, 138, 0.15)' : 'rgba(140, 158, 255, 0.15)',
                        color: r.is_colliding ? '#FF8A8A' : '#8C9EFF',
                      }}
                    >
                      :{r.port}/{r.proto}
                    </span>
                    <span style={{ fontWeight: 600, color: '#ECEEF3' }}>{r.name}</span>
                  </div>
                  <button
                    type="button"
                    className="c077"
                    aria-label={`Delete reservation for port ${r.port}`}
                    title="Delete reservation"
                    onClick={() => handleDeleteReservation(r.id, r.name)}
                  >
                    ✕
                  </button>
                </div>

                {r.is_colliding && (
                  <div style={{ fontSize: '11.5px', color: '#FF8A8A', background: 'rgba(255,92,92,0.1)', padding: '6px 8px', borderRadius: '6px' }}>
                    ⚠️ In use by active app: <strong>{r.colliding_app || 'Active Listener'}</strong>
                  </div>
                )}

                {r.description && (
                  <div style={{ fontSize: '12px', color: '#8D95A5' }}>{r.description}</div>
                )}

                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#64748B', marginTop: '4px' }}>
                  <span>Reserved by {r.created_by}</span>
                  <span>{r.service ? `Target: ${r.service}` : 'General Intent'}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
