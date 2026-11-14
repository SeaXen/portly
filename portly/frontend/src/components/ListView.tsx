import React from 'react';
import { AppItem, Category } from '../types';

interface ListViewProps {
  apps: AppItem[];
  onOpenDetail: (app: AppItem) => void;
  categories: Category[];
}

export const ListView: React.FC<ListViewProps> = ({ apps, onOpenDetail, categories }) => {
  return (
    <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '4px' }}>
      {apps.map((app) => (
        <div
          key={app.id}
          className="c053"
          style={{
            height: '40px',
            background: '#151821',
            border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: '8px',
            padding: '0 14px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            cursor: 'pointer',
          }}
          onClick={() => onOpenDetail(app)}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span
              style={{
                width: '7px',
                height: '7px',
                borderRadius: '50%',
                backgroundColor: app.status === 'up' ? '#5EEAD4' : '#FF8A8A',
              }}
            />
            <span style={{ fontWeight: 600, color: '#ECEEF3' }}>{app.name}</span>
            <span style={{ fontFamily: 'JetBrains Mono, monospace', color: '#8C9EFF', fontWeight: 600 }}>
              :{app.port}
            </span>
            <span style={{ fontSize: '12px', color: '#8D95A5' }}>
              {app.source === 'docker' ? app.image : app.process_name}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '12px', color: '#8D95A5' }}>
              {app.bind}
            </span>
            <span style={{ fontSize: '12px', color: '#8D95A5' }}>
              CPU {app.cpu_percent}% · {app.ram_mb} MB
            </span>
            <span className="c109" style={{ textTransform: 'capitalize' }}>
              {app.source}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
};
