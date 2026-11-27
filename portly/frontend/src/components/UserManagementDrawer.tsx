import React, { useCallback, useEffect, useState } from 'react';
import { Icon } from './Icon';
import { api } from '../api';
import { User } from '../types';
import { useFocusTrap } from '../hooks/useFocusTrap';
import { useToast } from './Toast';
import { ConfirmDialog } from './ConfirmDialog';

interface UserManagementDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  currentUser: any;
}

export function UserManagementDrawer({ isOpen, onClose, currentUser }: UserManagementDrawerProps) {
  const { success, error } = useToast();
  const containerRef = useFocusTrap<HTMLDivElement>(isOpen, onClose);
  const [activeTab, setActiveTab] = useState<'users' | 'audit'>('users');
  const [users, setUsers] = useState<User[]>([]);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  // New user form state
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState<'admin' | 'viewer'>('viewer');
  const [creating, setCreating] = useState(false);

  // Confirm delete dialog state
  const [deleteTarget, setDeleteTarget] = useState<User | null>(null);

  // Change password dialog state
  const [passwordTarget, setPasswordTarget] = useState<User | null>(null);
  const [newPwVal, setNewPwVal] = useState('');

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      if (activeTab === 'users') {
        const uList = await api.listUsers();
        setUsers(uList);
      } else {
        const logs = await api.getAuditLogs(100);
        setAuditLogs(logs);
      }
    } catch (e: any) {
      error(e.message || 'Failed to load user management data');
    } finally {
      setLoading(false);
    }
  }, [activeTab, error]);

  useEffect(() => {
    if (isOpen) {
      void loadData();
    }
  }, [isOpen, loadData]);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUsername.trim()) {
      error('Username is required.');
      return;
    }
    if (newPassword.length < 10) {
      error('Password must be at least 10 characters long.');
      return;
    }

    setCreating(true);
    try {
      await api.createUser({
        username: newUsername.trim(),
        password: newPassword,
        role: newRole,
      });
      success(`User '${newUsername}' created successfully.`);
      setNewUsername('');
      setNewPassword('');
      setNewRole('viewer');
      loadData();
    } catch (e: any) {
      error(e.message || 'Failed to create user');
    } finally {
      setCreating(false);
    }
  };

  const handleRoleChange = async (userId: string, role: string) => {
    try {
      await api.updateUserRole(userId, role);
      success('User role updated.');
      loadData();
    } catch (e: any) {
      error(e.message || 'Failed to update user role');
    }
  };

  const handleDeleteUser = async () => {
    if (!deleteTarget) return;
    try {
      await api.deleteUser(deleteTarget.id);
      success(`User '${deleteTarget.username}' deleted.`);
      setDeleteTarget(null);
      loadData();
    } catch (e: any) {
      error(e.message || 'Failed to delete user');
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!passwordTarget) return;
    if (newPwVal.length < 10) {
      error('Password must be at least 10 characters long.');
      return;
    }
    try {
      await api.updateUserPassword(passwordTarget.id, { new_password: newPwVal });
      success(`Password updated for '${passwordTarget.username}'.`);
      setPasswordTarget(null);
      setNewPwVal('');
    } catch (e: any) {
      error(e.message || 'Failed to update password');
    }
  };

  if (!isOpen) return null;

  return (
    <>
      <div
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0, 0, 0, 0.65)',
          backdropFilter: 'blur(3px)',
          zIndex: 8000,
        }}
        onClick={onClose}
      />
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="user-mgmt-title"
        style={{
          position: 'fixed',
          top: 0,
          right: 0,
          bottom: 0,
          width: '100%',
          maxWidth: 580,
          background: 'var(--surface-1)',
          borderLeft: '1px solid var(--border-strong)',
          zIndex: 8001,
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '-8px 0 32px rgba(0, 0, 0, 0.8)',
          fontFamily: 'Inter, system-ui, sans-serif',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '20px 24px',
            borderBottom: '1px solid var(--border-strong)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <h2 id="user-mgmt-title" style={{ margin: 0, fontSize: 18, fontWeight: 600, color: 'var(--text)' }}>
              Access & Security
            </h2>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--muted)' }}>Manage users, roles, and audit trail</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 0,
              color: 'var(--muted)',
              fontSize: 20,
              cursor: 'pointer',
              padding: 6,
            }}
            aria-label="Close user management drawer"
          >
            <Icon name="x" size={13} />
          </button>
        </div>

        {/* Tab switcher */}
        <div style={{ display: 'flex', borderBottom: '1px solid var(--border-strong)', padding: '0 24px', gap: 16 }}>
          <button
            type="button"
            onClick={() => setActiveTab('users')}
            style={{
              padding: '12px 4px',
              background: 'transparent',
              border: 0,
              borderBottom: activeTab === 'users' ? '2px solid var(--accent)' : '2px solid transparent',
              color: activeTab === 'users' ? 'var(--text)' : 'var(--muted)',
              fontWeight: 500,
              fontSize: 14,
              cursor: 'pointer',
            }}
          >
            Users ({users.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('audit')}
            style={{
              padding: '12px 4px',
              background: 'transparent',
              border: 0,
              borderBottom: activeTab === 'audit' ? '2px solid var(--accent)' : '2px solid transparent',
              color: activeTab === 'audit' ? 'var(--text)' : 'var(--muted)',
              fontWeight: 500,
              fontSize: 14,
              cursor: 'pointer',
            }}
          >
            Audit Logs
          </button>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 24 }}>
          {activeTab === 'users' ? (
            <>
              {/* User list */}
              <div>
                <h3 style={{ margin: '0 0 12px', fontSize: 14, color: 'var(--muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                  Active Accounts
                </h3>
                {loading ? (
                  <div style={{ color: 'var(--muted)', fontSize: 13 }}>Loading accounts…</div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {users.map((u) => {
                      const isSelf = currentUser && (currentUser.user_id === u.id || currentUser.username === u.username);
                      return (
                        <div
                          key={u.id}
                          style={{
                            background: 'var(--surface-input)',
                            border: '1px solid var(--border-strong)',
                            borderRadius: 10,
                            padding: '12px 16px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            gap: 12,
                          }}
                        >
                          <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <span style={{ fontWeight: 600, color: 'var(--text)', fontSize: 14 }}>{u.username}</span>
                              {isSelf && (
                                <span style={{ fontSize: 11, background: 'var(--accent-surface)', color: 'var(--accent)', padding: '1px 6px', borderRadius: 4 }}>
                                  You
                                </span>
                              )}
                            </div>
                            <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 2 }}>ID: {u.id}</div>
                          </div>

                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <select
                              aria-label={`Role for ${u.username}`}
                              value={u.role}
                              onChange={(e) => handleRoleChange(u.id, e.target.value)}
                              disabled={isSelf}
                              style={{
                                background: 'var(--surface-1)',
                                border: '1px solid var(--border-strong)',
                                color: 'var(--text)',
                                borderRadius: 6,
                                padding: '4px 8px',
                                fontSize: 13,
                              }}
                            >
                              <option value="admin">Admin</option>
                              <option value="viewer">Viewer</option>
                            </select>

                            <button
                              type="button"
                              onClick={() => {
                                setPasswordTarget(u);
                                setNewPwVal('');
                              }}
                              title="Change password"
                              style={{
                                background: 'var(--border-strong)',
                                border: 0,
                                borderRadius: 6,
                                color: 'var(--text)',
                                padding: '6px 10px',
                                fontSize: 12,
                                cursor: 'pointer',
                              }}
                            >
                              Password
                            </button>

                            {!isSelf && (
                              <button
                                type="button"
                                onClick={() => setDeleteTarget(u)}
                                title="Delete user"
                                style={{
                                  background: 'rgba(255, 77, 77, 0.15)',
                                  border: 0,
                                  borderRadius: 6,
                                  color: 'var(--danger)',
                                  padding: '6px 10px',
                                  fontSize: 12,
                                  cursor: 'pointer',
                                }}
                              >
                                Delete
                              </button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Create User Form */}
              <div style={{ background: 'var(--surface-input)', border: '1px solid var(--border-strong)', borderRadius: 12, padding: 20 }}>
                <h3 style={{ margin: '0 0 16px', fontSize: 15, fontWeight: 600, color: 'var(--text)' }}>Add New User</h3>
                <form onSubmit={handleCreateUser} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <label style={{ fontSize: 12, color: 'var(--muted)' }}>Username</label>
                    <input
                      aria-label="Username"
                      type="text"
                      name="new_username"
                      autoComplete="username"
                      value={newUsername}
                      onChange={(e) => setNewUsername(e.target.value)}
                      placeholder="e.g. dev_operator"
                      style={{
                        height: 38,
                        borderRadius: 6,
                        border: '1px solid var(--border-strong)',
                        background: 'var(--surface-1)',
                        color: 'var(--text)',
                        padding: '0 12px',
                        fontSize: 13,
                        outline: 'none',
                      }}
                    />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <label style={{ fontSize: 12, color: 'var(--muted)' }}>Password (min 10 characters)</label>
                    <input
                      aria-label="Password (min 10 characters)"
                      type="password"
                      name="new_password"
                      autoComplete="new-password"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      placeholder="••••••••••••"
                      style={{
                        height: 38,
                        borderRadius: 6,
                        border: '1px solid var(--border-strong)',
                        background: 'var(--surface-1)',
                        color: 'var(--text)',
                        padding: '0 12px',
                        fontSize: 13,
                        outline: 'none',
                      }}
                    />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <label style={{ fontSize: 12, color: 'var(--muted)' }}>Role</label>
                    <select
                      aria-label="Role"
                      value={newRole}
                      onChange={(e) => setNewRole(e.target.value as 'admin' | 'viewer')}
                      style={{
                        height: 38,
                        borderRadius: 6,
                        border: '1px solid var(--border-strong)',
                        background: 'var(--surface-1)',
                        color: 'var(--text)',
                        padding: '0 12px',
                        fontSize: 13,
                        outline: 'none',
                      }}
                    >
                      <option value="viewer">Viewer (Read-only)</option>
                      <option value="admin">Administrator (Full mutations)</option>
                    </select>
                  </div>

                  <button
                    type="submit"
                    disabled={creating}
                    style={{
                      height: 38,
                      borderRadius: 6,
                      border: 0,
                      background: 'var(--accent)',
                      color: 'var(--on-accent)',
                      fontWeight: 600,
                      fontSize: 13,
                      cursor: creating ? 'not-allowed' : 'pointer',
                      marginTop: 6,
                    }}
                  >
                    {creating ? 'Creating…' : 'Create Account'}
                  </button>
                </form>
              </div>
            </>
          ) : (
            <div>
              <h3 style={{ margin: '0 0 12px', fontSize: 14, color: 'var(--muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                Audit Trail (Last 100 Events)
              </h3>
              {loading ? (
                <div style={{ color: 'var(--muted)', fontSize: 13 }}>Loading audit logs…</div>
              ) : auditLogs.length === 0 ? (
                <div style={{ color: 'var(--muted)', fontSize: 13 }}>No audit logs recorded yet.</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {auditLogs.map((log, idx) => {
                    const ts = log.ts ?? log.timestamp;
                    return (
                    <div
                      key={log.id || idx}
                      style={{
                        background: 'var(--surface-input)',
                        border: '1px solid var(--border-strong)',
                        borderRadius: 8,
                        padding: '10px 14px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 4,
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12 }}>
                        <span style={{ fontWeight: 600, color: 'var(--accent)', fontFamily: 'monospace' }}>{log.event_type || log.type}</span>
                        <span style={{ color: 'var(--muted)' }}>{ts ? new Date(ts * 1000).toLocaleString() : ''}</span>
                      </div>
                      <div style={{ fontSize: 13, color: 'var(--text)' }}>{log.message}</div>
                      {log.actor && (
                        <div style={{ fontSize: 11, color: 'var(--success)' }}>Actor: {log.actor}</div>
                      )}
                    </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Confirm Delete User Dialog */}
      <ConfirmDialog
        isOpen={!!deleteTarget}
        title="Delete User Account"
        message={`Are you sure you want to delete user '${deleteTarget?.username}'? All their active sessions will be terminated.`}
        confirmLabel="Delete User"
        isDanger={true}
        onConfirm={handleDeleteUser}
        onCancel={() => setDeleteTarget(null)}
      />

      {/* Change Password Dialog */}
      {passwordTarget && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.7)',
            zIndex: 9000,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 20,
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setPasswordTarget(null);
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            style={{
              background: 'var(--surface-input)',
              border: '1px solid var(--border-strong)',
              borderRadius: 14,
              padding: 24,
              maxWidth: 400,
              width: '100%',
              display: 'flex',
              flexDirection: 'column',
              gap: 16,
            }}
          >
            <h3 style={{ margin: 0, fontSize: 17, fontWeight: 600, color: 'var(--text)' }}>
              Change Password: {passwordTarget.username}
            </h3>
            <form onSubmit={handleChangePassword} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label style={{ fontSize: 12, color: 'var(--muted)' }}>New Password (min 10 chars)</label>
                <input
                  aria-label="New Password (min 10 chars)"
                  type="password"
                  name="reset_password"
                  autoComplete="new-password"
                  value={newPwVal}
                  onChange={(e) => setNewPwVal(e.target.value)}
                  placeholder="••••••••••••"
                  autoFocus
                  style={{
                    height: 38,
                    borderRadius: 6,
                    border: '1px solid var(--border-strong)',
                    background: 'var(--surface-1)',
                    color: 'var(--text)',
                    padding: '0 12px',
                    fontSize: 13,
                    outline: 'none',
                  }}
                />
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 4 }}>
                <button
                  type="button"
                  onClick={() => setPasswordTarget(null)}
                  style={{
                    padding: '8px 14px',
                    borderRadius: 6,
                    border: '1px solid var(--border-strong)',
                    background: 'var(--surface-3)',
                    color: 'var(--text)',
                    fontSize: 13,
                    cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  style={{
                    padding: '8px 16px',
                    borderRadius: 6,
                    border: 0,
                    background: 'var(--accent)',
                    color: 'var(--on-accent)',
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Save Password
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
