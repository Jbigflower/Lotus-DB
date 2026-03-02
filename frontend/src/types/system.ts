// 系统状态与管理类型定义：与后端 models/schemas 完全对齐

export enum LogType {
  app = "app",
  error = "error",
  performance = "performance",
  worker_all = "worker_all",
  worker_error = "worker_error",
}

export interface HealthCheckItem {
  name: string;
  status: string; // ok/error
  latency_ms?: number | null;
  details?: Record<string, string> | null;
  message?: string | null;
}

export interface SystemHealthStatus {
  overall: string; // ok/degraded/error
  items: HealthCheckItem[];
}

export interface VersionInfo {
  app_name: string;
  app_version: string;
  environment: string;
}

export interface SystemStatus {
  timestamp: string;
  app: Record<string, string>;
  db: Record<string, Record<string, unknown>>;
}

export enum ConfigCategory {
  app = "app",
  database = "database",
  media = "media",
  llm = "llm",
}

export interface ConfigPatchRequest {
  category: ConfigCategory;
  updates: Record<string, string>;
}

export interface ConfigPatchResult {
  updated_keys: string[];
  restart_required: boolean;
  preview: Record<string, string>;
}

export interface LogFetchResponse {
  log_type: LogType;
  lines: number;
  content: string[];
}

// 资源占用类型映射（src/models/system/system_models.py）
export interface FolderUsage {
  path: string;
  exists: boolean;
  size_bytes: number;
  file_count: number;
  dir_count: number;
}

export interface ProcessUsage {
  cpu_percent?: number | null;
  memory_percent?: number | null;
  memory_bytes?: number | null;
}

export interface SystemUsage {
  cpu_percent?: number | null;
  memory_total?: number | null;
  memory_used?: number | null;
  memory_percent?: number | null;
}

export interface ResourceUsage {
  timestamp: string;
  process: ProcessUsage;
  system: SystemUsage;
  disk: Record<string, FolderUsage>;
}

export interface UserActivity {
  username: string;
  session_id: string;
  ip?: string | null;
  location?: string | null;
  device?: string | null;
  platform?: string | null;
  login_at?: string | null;
  last_active_at?: string | null;
}

export interface UserActivityList {
  items: UserActivity[];
}

// 路由层 Schema 别名（与后端 routers/schemas 保持同名）
export type HealthResponseSchema = SystemHealthStatus;
export type StatusResponseSchema = SystemStatus;
export type VersionResponseSchema = VersionInfo;
export type ConfigPatchRequestSchema = ConfigPatchRequest;
export type ConfigPatchResponseSchema = ConfigPatchResult;
export type UserActivityResponseSchema = UserActivityList;

// 查询日志的请求模型（后端为 LogQuerySchema）
export interface LogQuerySchema {
  type: LogType;
  lines?: number; // 默认 100（后端限制 1~2000）
}

// 便捷类型：Ping 响应
export interface PingResponse {
  status: string;
  router: string;
}