import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { tasks } from "@/api";
import { TaskStatus } from "@/types/task";
import type {
  TaskType,
  TaskSubType,
  TaskPriority,
  TaskRead,
  TaskPageResult,
  ProgressInfo,
} from "@/types/task";
import type { ListTasksParams } from "@/api/tasks";

type SortKey = "created_at" | "updated_at" | "priority" | "status" | "progress";
type SortOrder = "asc" | "desc";

function toMessage(e: unknown): string {
  if (e instanceof Error) return e.message;
  if (typeof e === "string") return e;
  try { return JSON.stringify(e); } catch { return String(e); }
}

export const useTasksStore = defineStore("tasks", () => {
  // 规范化字典与列表
  const entities = ref<Record<string, TaskRead>>({});
  const list = ref<TaskRead[]>([]);
  const listMeta = ref({ total: 0, page: 1, size: 20, pages: 0 });

  // 当前任务
  const currentId = ref<string | null>(null);
  const currentTask = computed<TaskRead | null>(() => {
    const id = currentId.value;
    return id ? entities.value[id] ?? list.value.find(i => i.id === id) ?? null : null;
  });

  // 列表筛选（与 API 参数一致）
  const filters = ref<ListTasksParams>({
    page: 1,
    size: 20,
    query: undefined,
    task_type: undefined,
    sub_type: undefined,
    status: undefined,
    priority: undefined,
    user_id: undefined,
  });

  // 排序
  const sortKey = ref<SortKey>("created_at");
  const sortOrder = ref<SortOrder>("desc");

  // UI 选择集（批量操作预留）
  const selectedIds = ref<Set<string>>(new Set());

  // 通用状态
  const loading = ref(false);
  const error = ref<string | null>(null);

  // 状态聚合
  const countsByStatus = computed<Record<TaskStatus, number>>(() => {
    const init: Record<TaskStatus, number> = {
      [TaskStatus.PENDING]: 0,
      [TaskStatus.RUNNING]: 0,
      [TaskStatus.COMPLETED]: 0,
      [TaskStatus.FAILED]: 0,
      [TaskStatus.CANCELLED]: 0,
      [TaskStatus.PAUSED]: 0,
      [TaskStatus.RETRYING]: 0,
    };
    for (const i of list.value) init[i.status] = (init[i.status] ?? 0) + 1;
    return init;
  });

  // 进度百分比
  const progressPercentById = computed<Record<string, number>>(() => {
    const out: Record<string, number> = {};
    for (const item of list.value) {
      const total = item.progress?.total_steps ?? 0;
      const done = item.progress?.completed_steps ?? 0;
      const ratio = total > 0 ? done / total : 0;
      out[item.id] = Math.max(0, Math.min(1, ratio));
    }
    return out;
  });

  // 排序后的列表
  const sortedList = computed<TaskRead[]>(() => {
    const base = [...list.value];
    const key = sortKey.value;
    const order = sortOrder.value;
    const statusOrder: Record<TaskStatus, number> = {
      [TaskStatus.RUNNING]: 100,
      [TaskStatus.PENDING]: 90,
      [TaskStatus.RETRYING]: 80,
      [TaskStatus.PAUSED]: 70,
      [TaskStatus.FAILED]: 60,
      [TaskStatus.CANCELLED]: 50,
      [TaskStatus.COMPLETED]: 10,
    };
    const getVal = (i: TaskRead): number => {
      switch (key) {
        case "created_at": return new Date(i.created_at).getTime() || 0;
        case "updated_at": return new Date(i.updated_at).getTime() || 0;
        case "priority": return i.priority ?? 0;
        case "status": return statusOrder[i.status] ?? 0;
        case "progress": {
          const t = i.progress?.total_steps ?? 0;
          const d = i.progress?.completed_steps ?? 0;
          return t > 0 ? d / t : 0;
        }
      }
    };
    base.sort((a, b) => {
      const va = getVal(a);
      const vb = getVal(b);
      return order === "asc" ? va - vb : vb - va;
    });
    return base;
  });

  function upsertEntity(item: TaskRead) {
    entities.value[item.id] = item;
    if (currentId.value === item.id) {
      // 保持 currentTask 计算属性同步
    }
  }
  function upsertEntities(items: TaskRead[]) {
    for (const it of items) upsertEntity(it);
  }

  // 选择集
  function toggleSelect(id: string) {
    if (selectedIds.value.has(id)) selectedIds.value.delete(id);
    else selectedIds.value.add(id);
  }
  function clearSelection() { selectedIds.value.clear(); }

  // 设置排序与筛选
  function setSort(key: SortKey, order: SortOrder = "desc") {
    sortKey.value = key; sortOrder.value = order;
  }
  function setFilters(partial: Partial<ListTasksParams>) {
    filters.value = { ...filters.value, ...partial };
  }
  function setPage(page: number) { filters.value.page = Math.max(1, page); }
  function setSize(size: number) { filters.value.size = Math.max(1, size); }

  // 列表
  async function fetchList(
    token: string,
    partial?: Partial<ListTasksParams>,
    options?: { baseURL?: string; signal?: AbortSignal }
  ): Promise<TaskPageResult> {
    loading.value = true; error.value = null;
    try {
      const params = { ...filters.value, ...(partial ?? {}) };
      const res = await tasks.listTasks(token, params, options);
      list.value = res.items ?? [];
      listMeta.value = {
        total: res.total ?? list.value.length,
        page: res.page ?? params.page ?? 1,
        size: res.size ?? params.size ?? list.value.length,
        pages: res.pages ?? 1,
      };
      upsertEntities(list.value);
      // 同步 filters 当前页与大小
      filters.value.page = listMeta.value.page;
      filters.value.size = listMeta.value.size;
      return res;
    } catch (e) {
      error.value = toMessage(e); throw e;
    } finally {
      loading.value = false;
    }
  }

  // 详情
  async function fetchById(
    token: string,
    taskId: string,
    options?: { baseURL?: string; signal?: AbortSignal }
  ): Promise<TaskRead> {
    loading.value = true; error.value = null;
    try {
      const res = await tasks.getTaskDetail(token, taskId, options);
      upsertEntity(res);
      currentId.value = res.id;
      // 同步列表项
      const idx = list.value.findIndex(i => i.id === res.id);
      if (idx >= 0) list.value.splice(idx, 1, res);
      return res;
    } catch (e) {
      error.value = toMessage(e); throw e;
    } finally {
      loading.value = false;
    }
  }

  // 取消
  async function cancel(
    token: string,
    taskId: string,
    options?: { baseURL?: string; signal?: AbortSignal }
  ): Promise<TaskRead> {
    loading.value = true; error.value = null;
    try {
      const res = await tasks.cancelTask(token, taskId, options);
      upsertEntity(res);
      const idx = list.value.findIndex(i => i.id === res.id);
      if (idx >= 0) list.value.splice(idx, 1, res);
      return res;
    } catch (e) {
      error.value = toMessage(e); throw e;
    } finally {
      loading.value = false;
    }
  }

  // 重试
  async function retry(
    token: string,
    taskId: string,
    options?: { baseURL?: string; signal?: AbortSignal }
  ): Promise<TaskRead> {
    loading.value = true; error.value = null;
    try {
      const res = await tasks.retryTask(token, taskId, options);
      upsertEntity(res);
      const idx = list.value.findIndex(i => i.id === res.id);
      if (idx >= 0) list.value.splice(idx, 1, res);
      return res;
    } catch (e) {
      error.value = toMessage(e); throw e;
    } finally {
      loading.value = false;
    }
  }

  // 删除
  async function remove(
    token: string,
    taskId: string,
    options?: { baseURL?: string; signal?: AbortSignal }
  ): Promise<boolean> {
    loading.value = true; error.value = null;
    try {
      const res = await tasks.deleteTask(token, taskId, options);
      if (res) {
        if (entities.value[taskId]) delete entities.value[taskId];
        const idx = list.value.findIndex(i => i.id === taskId);
        if (idx >= 0) list.value.splice(idx, 1);
        if (selectedIds.value.has(taskId)) selectedIds.value.delete(taskId);
      }
      return res;
    } catch (e) {
      error.value = toMessage(e); throw e;
    } finally {
      loading.value = false;
    }
  }

  // 进度
  async function fetchProgress(
    token: string,
    taskId: string,
    options?: { baseURL?: string; signal?: AbortSignal }
  ): Promise<ProgressInfo> {
    // 独立不更新 loading，让详情或列表保持轻量刷新
    try {
      const res = await tasks.getTaskProgress(token, taskId, options);
      const item = entities.value[taskId] ?? list.value.find(i => i.id === taskId) ?? null;
      if (item) {
        const updated: TaskRead = { ...item, progress: res };
        upsertEntity(updated);
        const idx = list.value.findIndex(i => i.id === taskId);
        if (idx >= 0) list.value.splice(idx, 1, updated);
      }
      return res;
    } catch (e) {
      // 仅抛出，不写入 error
      throw e;
    }
  }

  // 刷新所有运行中任务的进度
  async function refreshProgressForRunning(
    token: string,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    const runningIds = list.value.filter(i => i.status === TaskStatus.RUNNING).map(i => i.id);
    await Promise.all(runningIds.map(id => fetchProgress(token, id, options).catch(() => {})));
  }

  // 自动刷新（列表 + 可选运行中进度）
  const autoRefreshTimer = ref<number | null>(null);
  async function startAutoRefresh(
    token: string,
    intervalMs = 3000,
    includeProgress = true,
    params?: Partial<ListTasksParams>,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    stopAutoRefresh();
    await fetchList(token, params, options);
    if (includeProgress) await refreshProgressForRunning(token, options);
    autoRefreshTimer.value = window.setInterval(async () => {
      try {
        await fetchList(token, params, options);
        if (includeProgress) await refreshProgressForRunning(token, options);
      } catch { /* ignore */ }
    }, Math.max(1000, intervalMs));
  }
  function stopAutoRefresh() {
    if (autoRefreshTimer.value !== null) {
      clearInterval(autoRefreshTimer.value);
      autoRefreshTimer.value = null;
    }
  }

  // 重置
  function reset() {
    entities.value = {};
    list.value = [];
    listMeta.value = { total: 0, page: 1, size: 20, pages: 0 };
    currentId.value = null;
    selectedIds.value.clear();
    loading.value = false;
    error.value = null;
    stopAutoRefresh();
  }

  return {
    // state
    entities, list, listMeta, filters, sortKey, sortOrder, currentId, currentTask, selectedIds,
    loading, error,

    // computed
    sortedList, countsByStatus, progressPercentById,

    // actions
    setSort, setFilters, setPage, setSize,
    toggleSelect, clearSelection,
    fetchList, fetchById, fetchProgress, refreshProgressForRunning,
    cancel, retry, remove,
    startAutoRefresh, stopAutoRefresh,
    reset,
  };
});
