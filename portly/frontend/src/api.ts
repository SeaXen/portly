import {
  AppItem,
  Category,
  CommandExecResponse,
  ComposeActionResult,
  ComposeInfo,
  ComposeStack,
  ConflictItem,
  DeployContainerPayload,
  DockerImageItem,
  DockerSystemDf,
  DockerVolumeItem,
  PortReservation,
  PreflightResponse,
  PruneResult,
  ProxyConfigResponse,
  Rule,
  StatsData,
  SystemStats,
  TlsCertInfo,
  User,
  ViewItem,
} from './types';

const API_BASE = '/api';

// Discovered ports live on the Portly host, but the backend emits localhost when
// no public_host is configured. Point those links at the dashboard host instead.
export function resolveAppUrl<T extends { open_url?: string; url_override?: string }>(item: T): T {
  if (!item.open_url || item.url_override || typeof window === 'undefined') return item;
  try {
    const url = new URL(item.open_url);
    if (['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) {
      // No-op rewrite: keep the same object identity so SSE ticks don't
      // invalidate every row's memoization when nothing changed.
      if (url.hostname === window.location.hostname) return item;
      url.hostname = window.location.hostname;
      return { ...item, open_url: url.toString() };
    }
  } catch {
    // Not an absolute URL - leave it untouched.
  }
  return item;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Portly-Client': '1',
      ...(options.headers || {}),
    },
  });

  if (res.status === 401) {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('portly:unauthorized'));
    }
  }

  if (!res.ok) {
    let errDetail: any;
    try {
      errDetail = await res.json();
    } catch {
      errDetail = { message: res.statusText };
    }
    const message = errDetail.detail?.message || errDetail.message || `Request failed with status ${res.status}`;
    const code = errDetail.detail?.code || errDetail.code || 'ERROR';
    const err = new Error(message) as any;
    err.code = code;
    err.status = res.status;
    const preflight = errDetail.detail?.preflight ?? errDetail.preflight;
    if (preflight) err.preflight = preflight;
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
    const data = await request<{
      apps: AppItem[];
      total: number;
      conflicts: ConflictItem[];
      docker_status: { available: boolean; message: string };
      last_scan: number;
    }>(`/apps?${q.toString()}`);
    return { ...data, apps: data.apps.map(resolveAppUrl) };
  },

  async getAppDetail(appId: string): Promise<{
    app: AppItem;
    health: { status: string; ok: boolean; latency_ms: number; code: number };
    health_history: Array<{ ts: number; ok: boolean; latency_ms: number }>;
    docker_inspect?: any;
  }> {
    const data = await request<{
      app: AppItem;
      health: { status: string; ok: boolean; latency_ms: number; code: number };
      health_history: Array<{ ts: number; ok: boolean; latency_ms: number }>;
      docker_inspect?: any;
    }>(`/apps/${encodeURIComponent(appId)}`);
    return { ...data, app: resolveAppUrl(data.app) };
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
  }): Promise<{ status: string; count: number; succeeded?: string[]; failed?: Array<{ id: string; error: string }> }> {
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

  async updateCustomApp(appId: string): Promise<any> {
    return request(`/apps/${encodeURIComponent(appId)}/update/custom`, { method: 'POST' });
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
    return request(`/categories/${encodeURIComponent(catId)}`, { method: 'DELETE' });
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
    return request(`/rules/${encodeURIComponent(ruleId)}`, { method: 'DELETE' });
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
    return request(`/views/${encodeURIComponent(viewId)}`, { method: 'DELETE' });
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

  async importBackup(backup: any): Promise<any> {
    return request('/import', { method: 'POST', body: JSON.stringify(backup) });
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

  async setupAdmin(data: { username: string; password: string; setup_token?: string }): Promise<any> {
    return request('/auth/setup', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async logout(): Promise<any> {
    return request('/auth/logout', { method: 'POST' });
  },

  // User Management
  async listUsers(): Promise<User[]> {
    return request('/users');
  },

  async createUser(payload: { username: string; password: string; role?: string }): Promise<{ status: string; user: User }> {
    return request('/users', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async deleteUser(userId: string): Promise<{ status: string; id: string }> {
    return request(`/users/${encodeURIComponent(userId)}`, { method: 'DELETE' });
  },

  async updateUserRole(userId: string, role: string): Promise<{ status: string; id: string; role: string }> {
    return request(`/users/${encodeURIComponent(userId)}/role`, {
      method: 'PATCH',
      body: JSON.stringify({ role }),
    });
  },

  async updateUserPassword(userId: string, payload: { new_password: string; current_password?: string }): Promise<{ status: string }> {
    return request(`/users/${encodeURIComponent(userId)}/password`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // Audit Logs
  async getAuditLogs(limit: number = 100): Promise<any[]> {
    return request(`/audit-logs?limit=${limit}`);
  },

  // Preflight Port Collision Check
  async checkPreflight(payload: { compose_content?: string; command?: string }): Promise<PreflightResponse> {
    return request('/ports/preflight', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // Reveal Environment Variables
  async revealEnv(appId: string): Promise<{ env: Record<string, string> }> {
    return request(`/apps/${encodeURIComponent(appId)}/inspect/reveal-env`);
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

  // Multi-Port Remapping
  async applyMultiPortChange(appId: string, mappings: Array<{ container_port: string; host_port: number; bind?: string }>): Promise<any> {
    return request(`/apps/${encodeURIComponent(appId)}/ports-multi`, {
      method: 'POST',
      body: JSON.stringify({ mappings }),
    });
  },

  // Docker Hygiene & Storage
  async getDockerSystemDf(): Promise<DockerSystemDf> {
    return request('/docker/system');
  },

  async getDockerImages(): Promise<DockerImageItem[]> {
    return request('/docker/images');
  },

  async getDockerVolumes(): Promise<DockerVolumeItem[]> {
    return request('/docker/volumes');
  },

  async pruneDockerSystem(): Promise<PruneResult> {
    return request('/docker/prune', { method: 'POST' });
  },

  // Docker Compose Stack Actions
  async executeComposeAction(project: string, action: 'restart' | 'stop' | 'start' | 'down'): Promise<ComposeActionResult> {
    return request(`/docker/compose/${encodeURIComponent(project)}/action`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    });
  },

  // Container Deployment
  async deployContainer(payload: DeployContainerPayload): Promise<{ status: string; container: string; id: string }> {
    return request('/docker/containers/deploy', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // Port Reservations & Intent Registry
  async getPortReservations(): Promise<{ reservations: PortReservation[] }> {
    return request('/ports/reservations');
  },

  async createPortReservation(data: {
    port: number;
    proto?: string;
    name: string;
    service?: string;
    description?: string;
  }): Promise<PortReservation> {
    return request('/ports/reservations', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async deletePortReservation(id: string): Promise<any> {
    return request(`/ports/reservations/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    });
  },

  // In-UI Docker Compose Stack Manager
  async getComposeStacks(): Promise<{ stacks: ComposeStack[] }> {
    return request('/stacks');
  },

  async getComposeStack(name: string): Promise<ComposeStack> {
    return request(`/stacks/${encodeURIComponent(name)}`);
  },

  async saveComposeStack(data: {
    name: string;
    compose_yaml: string;
    force?: boolean;
  }): Promise<any> {
    return request('/stacks', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async deleteComposeStack(name: string): Promise<any> {
    return request(`/stacks/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    });
  },

  async executeStackAction(
    name: string,
    action: 'up' | 'down' | 'restart' | 'stop'
  ): Promise<any> {
    return request(`/stacks/${encodeURIComponent(name)}/action`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    });
  },
};
