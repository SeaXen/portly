import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import { ToastProvider } from './components/Toast';
import { AuthGate } from './components/AuthGate';
import './styles/tokens.css';
import './styles/style.css';
import './styles/app.css';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <ToastProvider>
      <AuthGate>
        {(auth) => <App user={auth.user} onLogout={auth.logout} />}
      </AuthGate>
    </ToastProvider>
  </React.StrictMode>
);
