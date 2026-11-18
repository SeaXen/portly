import React, { useState } from 'react';
import { api } from '../api';

interface SetupScreenProps {
  onSetupSuccess: (user: any) => void;
}

export function SetupScreen({ onSetupSuccess }: SetupScreenProps) {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [setupToken, setSetupToken] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim()) {
      setError('Username cannot be empty.');
      return;
    }
    if (password.length < 10) {
      setError('Password must be at least 10 characters long.');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setError('');
    setLoading(true);
    try {
      const res = await api.setupAdmin({
        username: username.trim(),
        password,
        setup_token: setupToken.trim() || undefined,
      });
      onSetupSuccess(res);
    } catch (err: any) {
      setError(err.message || 'Setup failed. Please check your setup token or password.');
    } finally {
      setLoading(false);
    }
  };

  const isPasswordLongEnough = password.length >= 10;

  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'var(--bg)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
        fontFamily: 'Inter, system-ui, sans-serif',
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: 440,
          background: 'var(--surface-1)',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          borderRadius: 16,
          padding: 36,
          boxShadow: '0 24px 48px rgba(0, 0, 0, 0.6)',
          display: 'flex',
          flexDirection: 'column',
          gap: 24,
        }}
      >
        <div style={{ textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
          <div
            style={{
              width: 52,
              height: 52,
              borderRadius: 14,
              background: '#1D2A44',
              color: 'var(--accent)',
              fontSize: 26,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 8px 16px rgba(140, 158, 255, 0.15)',
            }}
          >
            ⚓
          </div>
          <h1 style={{ margin: '8px 0 0', fontSize: 22, fontWeight: 700, color: 'var(--text)' }}>Welcome to Portly</h1>
          <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)' }}>Create your primary administrator account</p>
        </div>

        {error && (
          <div
            role="alert"
            style={{
              background: 'rgba(255, 138, 138, 0.1)',
              border: '1px solid var(--danger)',
              color: 'var(--danger)',
              padding: '10px 14px',
              borderRadius: 8,
              fontSize: 13,
              lineHeight: 1.4,
            }}
          >
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <label htmlFor="setup-username" style={{ fontSize: 13, color: 'var(--muted)', fontWeight: 500 }}>
              Admin Username
            </label>
            <input
              id="setup-username"
              name="username"
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="admin"
              disabled={loading}
              style={{
                height: 42,
                borderRadius: 8,
                border: '1px solid #242C37',
                background: '#161B22',
                color: 'var(--text)',
                padding: '0 14px',
                fontSize: 14,
                outline: 'none',
              }}
            />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label htmlFor="setup-password" style={{ fontSize: 13, color: 'var(--muted)', fontWeight: 500 }}>
                Password (min 10 characters)
              </label>
              <span style={{ fontSize: 12, color: isPasswordLongEnough ? 'var(--success)' : 'var(--muted)' }}>
                {password.length}/10
              </span>
            </div>
            <input
              id="setup-password"
              name="password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••"
              disabled={loading}
              style={{
                height: 42,
                borderRadius: 8,
                border: `1px solid ${password.length > 0 && !isPasswordLongEnough ? 'var(--danger)' : '#242C37'}`,
                background: '#161B22',
                color: 'var(--text)',
                padding: '0 14px',
                fontSize: 14,
                outline: 'none',
              }}
            />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <label htmlFor="setup-confirm-password" style={{ fontSize: 13, color: 'var(--muted)', fontWeight: 500 }}>
              Confirm Password
            </label>
            <input
              id="setup-confirm-password"
              name="confirm_password"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="••••••••••••"
              disabled={loading}
              style={{
                height: 42,
                borderRadius: 8,
                border: '1px solid #242C37',
                background: '#161B22',
                color: 'var(--text)',
                padding: '0 14px',
                fontSize: 14,
                outline: 'none',
              }}
            />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <label htmlFor="setup-token" style={{ fontSize: 13, color: 'var(--muted)', fontWeight: 500 }}>
                Setup Token
              </label>
              <span style={{ fontSize: 11, color: 'var(--muted)' }}>Printed to console on server startup</span>
            </div>
            <input
              id="setup-token"
              name="setup_token"
              autoComplete="off"
              type="text"
              value={setupToken}
              onChange={(e) => setSetupToken(e.target.value)}
              placeholder="Paste token if prompted by server"
              disabled={loading}
              style={{
                height: 42,
                borderRadius: 8,
                border: '1px solid #242C37',
                background: '#161B22',
                color: 'var(--text)',
                padding: '0 14px',
                fontSize: 14,
                outline: 'none',
                fontFamily: 'monospace',
              }}
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            style={{
              height: 44,
              borderRadius: 8,
              border: 0,
              background: 'var(--success)',
              color: '#0B1220',
              fontWeight: 600,
              fontSize: 15,
              cursor: loading ? 'not-allowed' : 'pointer',
              marginTop: 8,
              opacity: loading ? 0.7 : 1,
              transition: 'opacity 0.15s ease',
            }}
          >
            {loading ? 'Setting up…' : 'Create Admin Account'}
          </button>
        </form>
      </div>
    </div>
  );
}
