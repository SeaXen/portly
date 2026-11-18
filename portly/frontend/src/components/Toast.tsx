import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import { ToastMessage } from '../types';
import { Icon } from './Icon';

interface ToastContextType {
  toast: (message: string, type?: ToastMessage['type'], duration?: number) => void;
  success: (message: string) => void;
  error: (message: string) => void;
  warning: (message: string) => void;
  info: (message: string) => void;
}

const ToastContext = createContext<ToastContextType | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    (message: string, type: ToastMessage['type'] = 'info', duration: number = 4000) => {
      const id = `t_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
      setToasts((prev) => [...prev, { id, type, message, duration }]);
      if (duration > 0) {
        setTimeout(() => removeToast(id), duration);
      }
    },
    [removeToast]
  );

  const success = useCallback((msg: string) => toast(msg, 'success'), [toast]);
  const error = useCallback((msg: string) => toast(msg, 'error', 6000), [toast]);
  const warning = useCallback((msg: string) => toast(msg, 'warning', 5000), [toast]);
  const info = useCallback((msg: string) => toast(msg, 'info'), [toast]);

  return (
    <ToastContext.Provider value={{ toast, success, error, warning, info }}>
      {children}
      <div
        style={{
          position: 'fixed',
          bottom: 24,
          right: 24,
          zIndex: 9999,
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
          pointerEvents: 'none',
          maxWidth: 420,
        }}
        aria-live="polite"
      >
        {toasts.map((t) => {
          const isErr = t.type === 'error';
          const isWarn = t.type === 'warning';
          const isSucc = t.type === 'success';

          const borderColor = isErr ? '#FF8A8A' : isWarn ? '#FBBF77' : isSucc ? '#5EEAD4' : '#8C9EFF';
          const iconName = isErr ? 'warning' : isWarn ? 'bolt' : isSucc ? 'check' : 'info';

          return (
            <div
              key={t.id}
              role={isErr ? 'alert' : 'status'}
              style={{
                pointerEvents: 'auto',
                background: '#161B22',
                border: `1px solid ${borderColor}`,
                borderRadius: 10,
                padding: '12px 16px',
                color: '#ECEEF3',
                fontSize: 14,
                boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                animation: 'fadeIn 0.2s ease-out',
              }}
            >
              <span style={{ display: 'inline-flex' }}><Icon name={iconName} size={16} color={borderColor} /></span>
              <span style={{ flex: 1, wordBreak: 'break-word', lineHeight: 1.4 }}>{t.message}</span>
              <button
                onClick={() => removeToast(t.id)}
                style={{
                  background: 'transparent',
                  border: 0,
                  color: '#8D95A5',
                  cursor: 'pointer',
                  fontSize: 16,
                  padding: 4,
                  lineHeight: 1,
                }}
                aria-label="Close notification"
              >
                <Icon name="x" size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    // Fallback if rendered outside provider
    return {
      toast: (msg: string) => console.log(msg),
      success: (msg: string) => console.log(msg),
      error: (msg: string) => console.error(msg),
      warning: (msg: string) => console.warn(msg),
      info: (msg: string) => console.info(msg),
    };
  }
  return ctx;
}
