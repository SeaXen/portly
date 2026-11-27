import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { UserManagementDrawer } from './UserManagementDrawer';
import { AppDetailModal } from './AppDetailModal';
import { AddAppModal } from './AddAppModal';
import { ToastProvider } from './Toast';
import { api } from '../api';
import type { AppItem } from '../types';

vi.mock('../api', () => ({
  api: {
    listUsers: vi.fn(),
    getAuditLogs: vi.fn(),
    getAppLogs: vi.fn(),
    checkPort: vi.fn(),
    getAppDetail: vi.fn(),
    checkPreflight: vi.fn(),
  },
}));

const listUsers = vi.mocked(api.listUsers);
const getAuditLogs = vi.mocked(api.getAuditLogs);
const getAppLogs = vi.mocked(api.getAppLogs);
const checkPort = vi.mocked(api.checkPort);
const getAppDetail = vi.mocked(api.getAppDetail);
const checkPreflight = vi.mocked(api.checkPreflight);

const baseHostApp: AppItem = {
  id: 'host:python:9000',
  name: 'Local Worker',
  port: 9000,
  proto: 'tcp',
  bind: '127.0.0.1',
  source: 'host',
  category_id: 'development',
  category_mode: 'auto',
  tags: [],
  pinned: false,
  hidden: false,
  sort_order: 0,
  status: 'up',
  local_only: true,
  open_url: 'http://127.0.0.1:9000',
  cpu_percent: 1.2,
  ram_mb: 32,
  uptime_sec: 120,
};

describe('Final pre-Docker regression fixes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listUsers.mockResolvedValue([]);
    getAppLogs.mockResolvedValue({ lines: [], count: 0 });
    checkPort.mockResolvedValue({ free: true, used_by: '' });
  });

  it('renders audit log timestamps from the backend ts field', async () => {
    const sampleTs = 1700000000;
    const expectedTsText = new Date(sampleTs * 1000).toLocaleString();
    getAuditLogs.mockResolvedValue([
      { id: 1, type: 'auth.login', ts: sampleTs, message: 'Admin logged in', actor: 'admin' },
    ]);

    render(
      <div id="portly-app-root">
        <ToastProvider>
          <UserManagementDrawer isOpen={true} onClose={vi.fn()} currentUser={{ username: 'admin' }} />
        </ToastProvider>
      </div>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Audit Logs' }));

    expect(await screen.findByText('Admin logged in')).toBeTruthy();
    expect(screen.getByText(expectedTsText)).toBeTruthy();
  });

  it('preserves equals signs in env values and disables port remap on host processes', async () => {
    getAppDetail.mockResolvedValue({
      app: {
        ...baseHostApp,
        id: 'custom:app1',
        source: 'custom',
        env: {
          DATABASE_URL: 'postgres://user:pass@localhost:5432/db?sslmode=require',
        },
      },
      health_history: [],
      docker_inspect: null,
    } as any);

    render(
      <div id="portly-app-root">
        <ToastProvider>
          <AppDetailModal
            app={baseHostApp}
            onClose={vi.fn()}
            categories={[]}
            safeMode={false}
            onRefreshApps={vi.fn()}
          />
        </ToastProvider>
      </div>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'env' }));
    expect(
      await screen.findByText('postgres://user:pass@localhost:5432/db?sslmode=require'),
    ).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'ports' }));
    await waitFor(() => {
      const applyBtn = screen.getByRole('button', { name: 'Apply and recreate' }) as HTMLButtonElement;
      expect(applyBtn.disabled).toBe(true);
    });
    expect(screen.getByRole('note')).toBeTruthy();
  });

  it('remaps only matching standalone port tokens without corrupting substrings', async () => {
    checkPreflight.mockResolvedValue({
      checked_ports: [80],
      has_collision: true,
      collisions: [
        {
          port: 80,
          proto: 'tcp',
          service_name: 'host-nginx',
          source: 'host',
        },
      ],
      details: [
        {
          requested_port: 80,
          free: false,
          suggested_port: 8081,
        },
      ],
    } as any);

    render(
      <div id="portly-app-root">
        <ToastProvider>
          <AddAppModal
            onClose={vi.fn()}
            categories={[]}
            availableApps={[]}
            onAppAdded={vi.fn()}
          />
        </ToastProvider>
      </div>,
    );

    fireEvent.click(screen.getByRole('button', { name: /Preflight Collision Check/i }));
    const textarea = screen.getByLabelText(/Command Line Invocation/i) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: 'docker run -d -p 80:8080 nginx' } });

    fireEvent.click(screen.getByRole('button', { name: 'Run Preflight Check' }));
    const remapBtn = await screen.findByRole('button', { name: /Use Free :8081/i });
    fireEvent.click(remapBtn);

    expect(textarea.value).toBe('docker run -d -p 8081:8080 nginx');
  });
});
