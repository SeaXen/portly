export interface AppItem {
  id: string;
  source: 'host' | 'docker' | 'custom';
  name: string;
  process_name?: string;
  port: number;
  proto: string;
  bind: string;
  status: 'up' | 'down' | 'conflict';
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
  cpu_percent: number;
  ram_mb: number;
  uptime_sec: number;
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
  interfaces: Array<{
    name: string;
    ip: string;
    is_up: boolean;
    speed: number;
  }>;
}
