import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AuthGate } from './AuthGate';
import { api } from '../api';

vi.mock('../api', () => ({
  api: {
    getAuthMe: vi.fn(),
    login: vi.fn(),
    setupAdmin: vi.fn(),
    logout: vi.fn(),
  },
}));

const getAuthMe = vi.mocked(api.getAuthMe);

describe('AuthGate', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows the setup screen when needs_setup is true', async () => {
    getAuthMe.mockResolvedValue({ authenticated: false, needs_setup: true } as any);
    render(<AuthGate>{() => <div>DASHBOARD</div>}</AuthGate>);

    expect(await screen.findByText('Welcome to Portly')).toBeTruthy();
    expect(screen.queryByText('DASHBOARD')).toBeNull();
  });

  it('shows the login screen when unauthenticated', async () => {
    getAuthMe.mockResolvedValue({ authenticated: false, needs_setup: false } as any);
    render(<AuthGate>{() => <div>DASHBOARD</div>}</AuthGate>);

    expect(await screen.findByText('Sign in to manage ports and containers')).toBeTruthy();
    expect(screen.queryByText('DASHBOARD')).toBeNull();
  });

  it('renders children with the auth context when authenticated', async () => {
    getAuthMe.mockResolvedValue({
      authenticated: true,
      needs_setup: false,
      user: { username: 'admin' },
    } as any);
    render(<AuthGate>{(auth) => <div>DASHBOARD {auth.user.username}</div>}</AuthGate>);

    expect(await screen.findByText('DASHBOARD admin')).toBeTruthy();
  });
});
