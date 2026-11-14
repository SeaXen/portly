import {
  AppItem,
  Category,
  CommandExecResponse,
  ComposeInfo,
  ConflictItem,
  ProxyConfigResponse,
  Rule,
  StatsData,
  SystemStats,
  TlsCertInfo,
  ViewItem,
} from './types';

const API_BASE = '/api';

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  });

  if (!res.ok) {
    let errDetail: any = {};
    try {
      errDetail = await res.json();
    } catch {
      errDetail = { message: res.statusText };
    }
    const message = errDetail.detail?.message || errDetail.message || `Request failed with status ${res.status}`;
    const code = errDetail.detail?.code || errDetail.code || 'ERROR';
    const err = new Error(message) as any;
    err.code = code;
    throw err;
  }

  return res.json() as Promise<T>;
}

export const api = {
  // Apps
  async getApps(params: Record<string, any> = {}): Promise<{
    apps: AppItem[];
    total: number;
    conflicts: ConflictItem[];
    docker_status: { available: boolean; message: string };
    last_scan: number;
  }> {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') {
        q.append(k, String(v));
      }
    });
    return request(`/apps?${q.toString()}`);
  },

  async getAppDetail(appId: string): Promise<{
    app: AppItem;
    health: { status: string; ok: boolean; latency_ms: number; code: number };
    health_history: Array<{ ts: number; ok: boolean; latency_ms: number }>;
    docker_inspect?: any;
  }> {
    return request(`/apps/${encodeURIComponent(appId)}`);
  },

  async patchApp(appId: string, data: Partial<AppItem>): Promise<{ status: string; app: any }> {
    return request(`/apps/${encodeURIComponent(appId)}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  async bulkAction(data: {
    ids: string[];
    action: string;
    category_id?: string;
    tag?: string;
  }): Promise<{ status: string; count: number }> {
    return request('/apps/bulk', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  // Actions
  async startApp(appId: string): Promise<any> {
    return request(`/apps/${encodeURIComponent(appId)}/start`, { method: 'POST' });
  },

  async stopApp(appId: string): Promise<any> {
    return request(`/apps/${encodeURIComponent(appId)}/stop`, { method: 'POST' });
  },

  async restartApp(appId: string): Promise<any> {
    return request(`/apps/${encodeURIComponent(appId)}/restart`, { method: 'POST' });
  },

  async getAppLogs(appId: string, tail: number = 300): Promise<{ lines: string[]; count: number }> {
    return request(`/apps/${encodeURIComponent(appId)}/logs?tail=${tail}`);
  },

  // Port change & checking
  async checkPort(port: number, bind: string = '0.0.0.0'): Promise<{ free: boolean; used_by: string }> {
    return request(`/ports/check?port=${port}&bind=${bind}`);
  },

  async suggestPorts(start: number = 3000, count: number = 5, bind: string = '0.0.0.0'): Promise<{ suggested: number[] }> {
    return request(`/ports/suggest?start=${start}&count=${count}&bind=${bind}`);
  },

  async planPortChange(appId: string, hostPort: number, bind: string = '0.0.0.0'): Promise<{ plan: any }> {
    return request(`/apps/${encodeURIComponent(appId)}/port`, {
      method: 'POST',
      body: JSON.stringify({ host_port: hostPort, bind }),
    });
  },

  async applyPortChange(appId: string, hostPort: number, bind: string = '0.0.0.0'): Promise<any> {
    return request(`/apps/${encodeURIComponent(appId)}/port?apply=1`, {
      method: 'POST',
      body: JSON.stringify({ host_port: hostPort, bind }),
    });
  },

  async rollbackPortChange(appId: string): Promise<any> {
    return request(`/apps/${encodeURIComponent(appId)}/port?rollback=1`, {
      method: 'POST',
      body: JSON.stringify({ host_port: 0 }),
    });
  },

  // Image updates
  async checkImageUpdate(appId: string): Promise<any> {
    return request(`/apps/${encodeURIComponent(appId)}/update/check`, { method: 'POST' });
  },

  async applyImageUpdate(appId: string): Promise<any> {
    return request(`/apps/${encodeURIComponent(appId)}/update/apply`, { method: 'POST' });
  },

  // Custom apps
  async getCustomApps(): Promise<any[]> {
    return request('/custom-apps');
  },

  async saveCustomApp(appData: any): Promise<any> {
    return request('/custom-apps', {
      method: 'POST',
      body: JSON.stringify(appData),
    });
  },

  async deleteCustomApp(appId: string): Promise<any> {
    return request(`/custom-apps/${encodeURIComponent(appId)}`, { method: 'DELETE' });
  },

  // Stats & System
  async getStats(): Promise<StatsData> {
    return request('/stats');
  },

  async getSystemStats(): Promise<SystemStats> {
    return request('/system');
  },

  async getEvents(): Promise<any[]> {
    return request('/events');
  },

  // Categories
  async getCategories(): Promise<Category[]> {
    return request('/categories');
  },

  async saveCategory(cat: Partial<Category>): Promise<Category> {
    return request('/categories', {
      method: 'POST',
      body: JSON.stringify(cat),
    });
  },

  async deleteCategory(catId: string): Promise<any> {
    return request(`/categories/${catId}`, { method: 'DELETE' });
  },

  // Rules
  async getRules(): Promise<Rule[]> {
    return request('/rules');
  },

  async saveRule(rule: Partial<Rule>): Promise<Rule> {
    return request('/rules', {
      method: 'POST',
      body: JSON.stringify(rule),
    });
  },

  async deleteRule(ruleId: string): Promise<any> {
    return request(`/rules/${ruleId}`, { method: 'DELETE' });
  },

  // Views
  async getViews(): Promise<ViewItem[]> {
    return request('/views');
  },

  async saveView(view: ViewItem): Promise<ViewItem> {
    return request('/views', {
      method: 'POST',
      body: JSON.stringify(view),
    });
  },

  async deleteView(viewId: string): Promise<any> {
    return request(`/views/${viewId}`, { method: 'DELETE' });
  },

  // Settings
  async getSettings(): Promise<Record<string, string>> {
    return request('/settings');
  },

  async updateSettings(settings: Record<string, string>): Promise<Record<string, string>> {
    return request('/settings', {
      method: 'PATCH',
      body: JSON.stringify(settings),
    });
  },

  // Scan
  async triggerScan(): Promise<{ status: string; apps_count: number; conflicts: number }> {
    return request('/scan', { method: 'POST' });
  },

  // Export
  exportUrl(format: 'json' | 'csv' | 'markdown'): string {
    return `${API_BASE}/export?format=${format}`;
  },

  // Auth
  async getAuthMe(): Promise<{ authenticated: boolean; user?: any; needs_setup: boolean }> {
    return request('/auth/me');
  },

  async login(credentials: { username: string; password: string }): Promise<any> {
    return request('/auth/login', {
      method: 'POST',
      body: JSON.stringify(credentials),
    });
  },

  async setupAdmin(data: { username: string; password: string }): Promise<any> {
    return request('/auth/setup', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async logout(): Promise<any> {
    return request('/auth/logout', { method: 'POST' });
  },

  // Reverse Proxy Generator
  async getProxyConfig(appId: string, format?: string, domain?: string): Promise<ProxyConfigResponse> {
    const q = new URLSearchParams();
    if (format) q.append('format', format);
    if (domain) q.append('domain', domain);
    const qs = q.toString() ? `?${q.toString()}` : '';
    return request(`/apps/${encodeURIComponent(appId)}/proxy-config${qs}`);
  },

  // SSL/TLS Certificate Inspector
  async getAppTls(appId: string): Promise<TlsCertInfo> {
    return request(`/apps/${encodeURIComponent(appId)}/tls`);
  },

  // In-Browser Container Terminal Runner
  async execContainerCommand(appId: string, command: string, timeout: number = 10): Promise<CommandExecResponse> {
    return request(`/apps/${encodeURIComponent(appId)}/exec`, {
      method: 'POST',
      body: JSON.stringify({ command, timeout }),
    });
  },

  // Docker Compose Inspector
  async getAppCompose(appId: string): Promise<ComposeInfo> {
    return request(`/apps/${encodeURIComponent(appId)}/compose`);
  },

  // Webhook Test
  async testWebhook(data: { url?: string; type?: string; event?: string } = {}): Promise<{ status: string; message: string; url: string; type: string }> {
    return request('/settings/test-webhook', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};
