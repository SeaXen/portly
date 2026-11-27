export interface AppItem {
  id: string;
  source: 'host' | 'docker' | 'custom';
  name: string;
  process_name?: string;
  port: number;
  proto: string;
  bind: string;
  status: 'up' | 'down' | 'conflict' | 'unknown';
  health?: string;
  category_id: string;
  category_mode: 'auto' | 'manual';
  tags: string[];
  notes?: string;
  pinned: boolean;
  hidden: boolean;
  sort_order: number;
  open_url: string;
  url_override?: string;
  local_only: boolean;
  cpu_percent: number | null;
  ram_mb: number | null;
  uptime_sec: number | null;
  stats_age_sec?: number | null;
  pid?: number;
  cmdline?: string;
  cwd?: string;
  image?: string;
  container_name?: string;
  container_id?: string;
  compose_project?: string;
  compose_service?: string;
  health_path?: string;
  health_interval?: number;
  start_cmd?: string;
  stop_cmd?: string;
  workdir?: string;
  log_file?: string;
  icon?: string;
  has_tls?: boolean;
  tls_days_remaining?: number;
  tls_expired?: boolean;
  expected_status?: string;
  custom_headers?: Record<string, string>;
  env?: Record<string, string>;
}

export interface PortReservation {
  id: string;
  port: number;
  proto: string;
  name: string;
  service?: string;
  description?: string;
  created_by: string;
  created_at: number;
  is_colliding?: boolean;
  colliding_app?: string | null;
}

export interface ComposeStack {
  name: string;
  compose_yaml: string;
  status: 'running' | 'stopped';
  containers_running: number;
  ports: number[];
  created_at: number;
  updated_at: number;
}

export interface Category {
  id: string;
  name: string;
  color: string;
  mode: 'auto' | 'manual';
  sort_order: number;
  count?: number;
}

export interface Rule {
  id: string;
  category_id: string;
  field: string;
  operator: string;
  value: string;
  priority: number;
}

export interface ViewItem {
  id: string;
  name: string;
  filters: Record<string, any>;
  sort: Record<string, any>;
  group_by: string;
  view_type: 'table' | 'grid' | 'list' | 'board';
  columns: string[];
}

export interface StatMetric {
  label: string;
  value: string;
  context: string;
  percent?: number;
  conflict_count?: number;
  /** Disk only: false when PORTLY_HOSTFS is set but not mounted. */
  host_visible?: boolean;
  sparkline: string;
  history: number[];
}

export interface StatsData {
  cpu: StatMetric;
  memory: StatMetric;
  disk: StatMetric;
  network: StatMetric;
  containers: StatMetric;
  listening: StatMetric;
  ts: number;
}

export interface ConflictItem {
  port: number;
  apps: string[];
  ids: string[];
}

export interface SystemStats {
  platform: string;
  hostname: string;
  uptime: string;
  uptime_sec: number;
  cpu_per_core: number[];
  load_avg?: [number, number, number] | null;
  memory: {
    total_gb: number;
    used_gb: number;
    available_gb: number;
    percent: number;
  };
  swap: {
    total_gb: number;
    used_gb: number;
    percent: number;
  };
  disks: Array<{
    device: string;
    mountpoint: string;
    fstype: string;
    total_gb: number;
    used_gb: number;
    free_gb: number;
    percent: number;
  }>;
  /** False when PORTLY_HOSTFS is configured but not mounted. */
  host_visible?: boolean;
  /** True when X-Forwarded-For arrived without PORTLY_TRUSTED_PROXIES configured. */
  untrusted_proxy_detected?: boolean;
  interfaces: Array<{
    name: string;
    ip: string;
    is_up: boolean;
    speed: number;
  }>;
}

export interface ProxyConfigResponse {
  domain: string;
  upstream_host: string;
  port: number;
  router_name: string;
  configs: {
    caddy: string;
    nginx: string;
    traefik: string;
    traefik_yaml: string;
    traefik_labels: string;
    cloudflared?: string;
  };
}

export interface MultiPortItem {
  container_port: string;
  host_port: number;
  bind?: string;
}

export interface DockerSystemDf {
  available: boolean;
  images_count: number;
  containers_count: number;
  volumes_count: number;
  build_cache_count?: number;
  total_size_mb: number;
  total_reclaimable_mb: number;
  error?: string;
}

export interface DockerImageItem {
  id: string;
  full_id: string;
  tags: string[];
  primary_tag: string;
  size_mb: number;
  created: string;
}

export interface DockerVolumeItem {
  name: string;
  driver: string;
  mountpoint: string;
  created: string;
  labels: Record<string, string>;
}

export interface PruneResult {
  status: string;
  space_reclaimed_mb: number;
  deleted: {
    containers: string[];
    images: string[];
    volumes: string[];
    networks: string[];
  };
}

export interface ComposeActionResult {
  status: string;
  action: string;
  project: string;
  affected_containers: string[];
}

export interface DeployContainerPayload {
  image: string;
  name: string;
  ports: Record<string, number>;
  env?: Record<string, string>;
  volumes?: string[];
  restart_policy?: string;
}

export interface TlsCertInfo {
  is_tls: boolean;
  error?: string | null;
  subject?: string;
  issuer?: string;
  valid_from?: string;
  valid_until?: string;
  days_remaining?: number | null;
  expired: boolean;
  self_signed: boolean;
  san: string[];
  version?: number;
  serial_number?: string;
}

export interface CommandExecResponse {
  exit_code: number;
  output: string;
  command: string;
  duration_ms: number;
}

export interface ComposeInfo {
  has_compose: boolean;
  project?: string;
  service?: string;
  working_dir?: string;
  config_file?: string;
  content?: string | null;
  error?: string | null;
  message?: string;
}

export interface User {
  id: string;
  username: string;
  role: 'admin' | 'viewer';
  created_at: number;
}

export interface PreflightCollision {
  port: number;
  proto: string;
  bind?: string;
  conflict_with?: string;
  conflict_type?: string;
  service_name?: string;
  owner?: string;
  source?: string;
}

export interface PreflightDetail {
  requested_port: number;
  container_port: number;
  bind: string;
  proto: string;
  available: boolean;
  conflict_reason: string;
  suggested_port?: number | null;
  reserved?: boolean;
}

export interface PreflightResponse {
  valid: boolean;
  has_collision: boolean;
  has_conflicts: boolean;
  collisions: PreflightCollision[];
  ports: Array<{ port: number; proto: string; bind: string }>;
  checked_ports: number[];
  details?: PreflightDetail[];
  summary: string;
}

export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'info' | 'warning';
  message: string;
  duration?: number;
}

