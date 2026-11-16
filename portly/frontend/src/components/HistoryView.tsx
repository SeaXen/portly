import React, { useEffect, useState } from 'react';
import { api } from '../api';

export const HistoryView: React.FC = () => {
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadEvents();
  }, []);

  const loadEvents = async () => {
    try {
      const data = await api.getEvents();
      setEvents(data);
    } catch {} finally {
      setLoading(false);
    }
  };

  const getBadgeColor = (type: string) => {
    if (type.includes('start') || type.includes('open')) return '#5EEAD4';
    if (type.includes('stop') || type.includes('close')) return '#FF8A8A';
    if (type.includes('conflict')) return '#FF8A8A';
    if (type.includes('change') || type.includes('rollback')) return '#8C9EFF';
    return '#FBBF77';
  };

  return (
    <div style={{ background: '#101218', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '14px', padding: '24px', width: '100%', boxSizing: 'border-box' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 600, color: '#ECEEF3' }}>Change Log & System Events</h2>
          <div style={{ fontSize: '13px', color: '#8D95A5', marginTop: '4px' }}>
            Historical record of newly opened ports, closed sockets, container state changes, and management actions.
          </div>
        </div>
        <button type="button" className="c078" onClick={loadEvents}>
          Refresh Log
        </button>
      </div>

      {loading ? (
        <div style={{ padding: '40px', textAlign: 'center', color: '#8D95A5' }}>Loading event log…</div>
      ) : events.length === 0 ? (
        <div style={{ padding: '40px', textAlign: 'center', color: '#8D95A5', fontSize: '14px' }}>
          No system events recorded yet. Events trigger as ports open, close, or containers change status.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {events.map((evt) => {
            const dateStr = new Intl.DateTimeFormat(undefined, { dateStyle: 'short', timeStyle: 'medium' }).format(new Date(evt.ts * 1000));
            const badgeColor = getBadgeColor(evt.type);

            return (
              <div
                key={evt.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '12px 16px',
                  background: '#151821',
                  borderRadius: '10px',
                  border: '1px solid rgba(255,255,255,0.05)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                  <span
                    style={{
                      fontFamily: 'JetBrains Mono, monospace',
                      fontSize: '11px',
                      padding: '2px 8px',
                      borderRadius: '6px',
                      background: `${badgeColor}15`,
                      color: badgeColor,
                      border: `1px solid ${badgeColor}30`,
                      textTransform: 'uppercase',
                    }}
                  >
                    {evt.type.replace('_', ' ')}
                  </span>
                  <span style={{ fontSize: '14px', color: '#ECEEF3', fontWeight: 500 }}>
                    {evt.message}
                  </span>
                </div>

                <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '12px', color: '#8D95A5' }}>
                  {dateStr}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
