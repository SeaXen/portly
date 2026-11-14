import React from 'react';
import { AppItem, ConflictItem } from '../types';

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
  return (
    <div style={{ background: '#101218', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '14px', padding: '24px', width: '100%', boxSizing: 'border-box' }}>
      <div style={{ marginBottom: '20px' }}>
        <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 600, color: '#ECEEF3' }}>Port Conflicts & Collisions</h2>
        <div style={{ fontSize: '13px', color: '#8D95A5', marginTop: '4px' }}>
          Conflicts occur when two different processes or containers attempt to bind to the same host port.
        </div>
      </div>

      {conflicts.length === 0 ? (
        <div style={{ padding: '60px 24px', textAlign: 'center' }}>
          <div style={{ fontSize: '40px', marginBottom: '12px' }}>✓</div>
          <div style={{ fontSize: '16px', fontWeight: 600, color: '#5EEAD4', marginBottom: '6px' }}>No Port Conflicts Detected</div>
          <div style={{ fontSize: '13px', color: '#8D95A5', maxWidth: '420px', margin: '0 auto 20px auto' }}>
            Every active listener on your system has a unique, uncontested port assignment.
          </div>
          <button type="button" className="c078" onClick={() => onSelectNav('ports')}>
            View all ports →
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
  );
};
