import { http } from "./http";
import type {
  PingResponse,
  HealthResponseSchema,
  StatusResponseSchema,
  VersionResponseSchema,
  ConfigPatchRequestSchema,
  ConfigPatchResponseSchema,
  LogQuerySchema,
  LogFetchResponse,
  UserActivityResponseSchema,
} from "@/types/system";


// 映射前端枚举到后端枚举字符串（同步后端 LogType）
function mapLogTypeToBackend(t: LogQuerySchema["type"]): string {
  switch (t) {
    case "app":
    case "error":
    case "performance":
    case "worker_all":
    case "worker_error":
      return t;
    default:
      return String(t);
  }
}


/**
 * Ping：GET /api/v1/system/ping
 */
export async function ping(
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<PingResponse> {
  return http.get<PingResponse>("/api/v1/system/ping", {
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 健康检查：GET /api/v1/system/health
 */
export async function health(
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<HealthResponseSchema> {
  return http.get<HealthResponseSchema>("/api/v1/system/health", {
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 系统状态：GET /api/v1/system/status
 */
export async function status(
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<StatusResponseSchema> {
  return http.get<StatusResponseSchema>("/api/v1/system/status", {
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 版本信息：GET /api/v1/system/version
 */
export async function version(
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<VersionResponseSchema> {
  return http.get<VersionResponseSchema>("/api/v1/system/version", {
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 修改配置（管理员）：PATCH /api/v1/system/config
 */
export async function patchConfig(
  token: string,
  data: ConfigPatchRequestSchema,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<ConfigPatchResponseSchema> {
  return http.patch<ConfigPatchResponseSchema>("/api/v1/system/config", data, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 获取日志（管理员）：GET /api/v1/system/logs
 */
export async function getLogs(
  token: string,
  query: LogQuerySchema,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<LogFetchResponse> {
  const qp = new URLSearchParams();
  qp.append("type", mapLogTypeToBackend(query.type));
  if (query.lines) qp.append("lines", String(query.lines));

  return http.get<LogFetchResponse>(`/api/v1/system/logs?${qp.toString()}`, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 获取用户活动：GET /api/v1/system/activities
 */
export async function activities(
  token: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<UserActivityResponseSchema> {
  return http.get<UserActivityResponseSchema>("/api/v1/system/activities", {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 资源监控：GET /api/v1/system/resources
 */
export async function getResourceUsage(
  token?: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<import('@/types/system').ResourceUsage> {
  return http.get<import('@/types/system').ResourceUsage>("/api/v1/system/resources", {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 重启：POST /api/v1/system/restart
 */
export async function restart(
  token: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<{ ok: boolean; message?: string }> {
  return http.post<{ ok: boolean; message?: string }>("/api/v1/system/restart", undefined, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 关闭：POST /api/v1/system/shutdown
 */
export async function shutdown(
  token: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<{ ok: boolean; message?: string }> {
  return http.post<{ ok: boolean; message?: string }>("/api/v1/system/shutdown", undefined, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}
