import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { system } from "@/api";
import {
  type PingResponse,
  type HealthResponseSchema,
  type StatusResponseSchema,
  type VersionResponseSchema,
  type ConfigPatchRequestSchema,
  type ConfigPatchResponseSchema,
  LogType,
  type UserActivity,
} from "@/types/system";
import type {  LogQuerySchema, LogFetchResponse } from "@/types/system"

function toMessage(e: unknown): string {
  if (e instanceof Error) return e.message;
  if (typeof e === "string") return e;
  try { return JSON.stringify(e); } catch { return String(e); }
}

export const useSystemStore = defineStore("system", () => {
  // 基本状态
  const pingStatus = ref<PingResponse | null>(null);
  const health = ref<HealthResponseSchema | null>(null);
  const status = ref<StatusResponseSchema | null>(null);
  const version = ref<VersionResponseSchema | null>(null);
  const lastUpdated = ref<{ health?: string; status?: string; version?: string }>({});

  // 配置更新反馈
  const configResult = ref<ConfigPatchResponseSchema | null>(null);

  // 日志与过滤
  const logs = ref<LogFetchResponse | null>(null);
  const logFilters = ref<{ type: LogType; lines: number }>({
    type: LogType.app,
    lines: 200,
  });

  // 用户活动
  const activities = ref<UserActivity[]>([]);

  // 通用状态
  const loading = ref(false);
  const error = ref<string | null>(null);

  // 计算属性：健康项分类
  const healthyItems = computed(() => (health.value?.items ?? []).filter(i => i.status === "ok"));
  const unhealthyItems = computed(() => (health.value?.items ?? []).filter(i => i.status !== "ok"));

  // 计算属性：状态展开以便列表渲染
  const appStatusList = computed(() => {
    const rec = status.value?.app ?? {};
    return Object.keys(rec).map(k => ({ key: k, value: String(rec[k]) }));
  });
  const dbStatusList = computed(() => {
    const rec = status.value?.db ?? {};
    return Object.keys(rec).map(k => ({ key: k, value: rec[k] }));
  });

  // 计算属性：日志文本
  const logsText = computed(() => (logs.value?.content ?? []).join("\n"));

  // Ping
  async function ping(options?: { baseURL?: string; signal?: AbortSignal }) {
    try {
      const res = await system.ping(options);
      pingStatus.value = res;
      return res;
    } catch (e) {
      // ping 不阻塞页面流程，不写入 error
      throw e;
    }
  }

  // 健康
  async function fetchHealth(options?: { baseURL?: string; signal?: AbortSignal }) {
    loading.value = true; error.value = null;
    try {
      const res = await system.health(options);
      health.value = res;
      lastUpdated.value.health = new Date().toISOString();
      return res;
    } catch (e) {
      error.value = toMessage(e);
      throw e;
    } finally {
      loading.value = false;
    }
  }

  // 状态
  async function fetchStatus(options?: { baseURL?: string; signal?: AbortSignal }) {
    loading.value = true; error.value = null;
    try {
      const res = await system.status(options);
      status.value = res;
      lastUpdated.value.status = new Date().toISOString();
      return res;
    } catch (e) {
      error.value = toMessage(e);
      throw e;
    } finally {
      loading.value = false;
    }
  }

  // 版本
  async function fetchVersion(options?: { baseURL?: string; signal?: AbortSignal }) {
    loading.value = true; error.value = null;
    try {
      const res = await system.version(options);
      version.value = res;
      lastUpdated.value.version = new Date().toISOString();
      return res;
    } catch (e) {
      error.value = toMessage(e);
      throw e;
    } finally {
      loading.value = false;
    }
  }

  // 合并刷新（健康/状态/版本）
  async function refresh(options?: { baseURL?: string; signal?: AbortSignal }) {
    loading.value = true; error.value = null;
    try {
      const [h, s, v] = await Promise.all([
        system.health(options),
        system.status(options),
        system.version(options),
      ]);
      health.value = h; status.value = s; version.value = v;
      const now = new Date().toISOString();
      lastUpdated.value = { health: now, status: now, version: now };
      return { health: h, status: s, version: v };
    } catch (e) {
      error.value = toMessage(e);
      throw e;
    } finally {
      loading.value = false;
    }
  }

  // 配置更新（管理员）
  async function patchConfig(
    token: string,
    payload: ConfigPatchRequestSchema,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true; error.value = null;
    try {
      const res = await system.patchConfig(token, payload, options);
      configResult.value = res;
      return res;
    } catch (e) {
      error.value = toMessage(e);
      throw e;
    } finally {
      loading.value = false;
    }
  }

  // 日志查询（管理员）
  function setLogFilter(type?: LogType, lines?: number) {
    if (type !== undefined) logFilters.value.type = type;
    if (lines !== undefined) logFilters.value.lines = Math.max(1, Math.min(2000, lines));
  }

  async function fetchLogs(
    token: string,
    partial?: Partial<LogQuerySchema>,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true; error.value = null;
    try {
      const query: LogQuerySchema = {
        type: partial?.type ?? logFilters.value.type,
        lines: partial?.lines ?? logFilters.value.lines,
      };
      const res = await system.getLogs(token, query, options);
      logs.value = res;
      // 同步过滤器（若传入了 partial）
      logFilters.value.type = query.type;
      logFilters.value.lines = query.lines ?? logFilters.value.lines;
      return res;
    } catch (e) {
      error.value = toMessage(e);
      throw e;
    } finally {
      loading.value = false;
    }
  }

  function clearLogs() { logs.value = null; }

  // 获取用户活动
  async function fetchActivities(token: string, options?: { baseURL?: string; signal?: AbortSignal }) {
    loading.value = true;
    error.value = null;
    try {
      const res = await system.activities(token, options);
      activities.value = res.items;
      return res;
    } catch (e) {
      error.value = toMessage(e);
      throw e;
    } finally {
      loading.value = false;
    }
  }

  // 重置
  function reset() {
    pingStatus.value = null;
    health.value = null;
    status.value = null;
    version.value = null;
    configResult.value = null;
    logs.value = null;
    lastUpdated.value = {};
    error.value = null;
  }

  return {
    // state
    pingStatus, health, status, version, lastUpdated,
    configResult, logs, logFilters,
    activities,
    loading, error,

    // computed
    healthyItems, unhealthyItems,
    appStatusList, dbStatusList,
    logsText,

    // actions
    ping,
    fetchHealth, fetchStatus, fetchVersion, refresh,
    patchConfig,
    setLogFilter, fetchLogs, clearLogs,
    fetchActivities,
    reset,
  };
});