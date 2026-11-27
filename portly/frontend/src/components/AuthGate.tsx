import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { api } from '../api';
import { BrandMark } from './BrandMark';
import { LoginScreen } from './LoginScreen';
import { SetupScreen } from './SetupScreen';

interface AuthContextType {
  user: any;
  logout: () => Promise<void>;
  refreshAuth: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthGate');
  }
  return ctx;
}

export function AuthGate({ children }: { children: (auth: AuthContextType) => ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [needsSetup, setNeedsSetup] = useState(false);
  const [user, setUser] = useState<any>(null);

  const checkAuth = async () => {
    try {
      const res = await api.getAuthMe();
      setNeedsSetup(res.needs_setup);
      setAuthenticated(res.authenticated);
      setUser(res.user || null);
    } catch (e) {
      console.error('Error checking auth state:', e);
      setAuthenticated(false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkAuth();

    const handleUnauthorized = () => {
      setAuthenticated(false);
      setUser(null);
    };

    window.addEventListener('portly:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('portly:unauthorized', handleUnauthorized);
  }, []);

  const logout = async () => {
    try {
      await api.logout();
    } catch {
      // Ignored
    } finally {
      setAuthenticated(false);
      setUser(null);
      await checkAuth();
    }
  };

  if (loading) {
    return (
      <div
        style={{
          minHeight: '100vh',
          background: 'var(--bg)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 16,
          color: 'var(--muted)',
          fontFamily: 'Inter, system-ui, sans-serif',
        }}
      >
        <div style={{ color: 'var(--accent)', animation: 'spin 1.5s linear infinite', display: 'inline-flex' }}>
          <BrandMark size={36} />
        </div>
        <div style={{ fontSize: 14 }}>Connecting to Portly…</div>
      </div>
    );
  }

  if (needsSetup) {
    return (
      <SetupScreen
        onSetupSuccess={async (newUser) => {
          setUser(newUser);
          setNeedsSetup(false);
          setAuthenticated(true);
          await checkAuth();
        }}
      />
    );
  }

  if (!authenticated) {
    return (
      <LoginScreen
        onLoginSuccess={async (loggedUser) => {
          setUser(loggedUser);
          setAuthenticated(true);
          await checkAuth();
        }}
      />
    );
  }

  const authValue: AuthContextType = {
    user,
    logout,
    refreshAuth: checkAuth,
  };

  return <AuthContext.Provider value={authValue}>{children(authValue)}</AuthContext.Provider>;
}
