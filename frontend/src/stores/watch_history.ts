import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { player } from "@/api";
import type {
  WatchType,
  WatchHistoryRead,
  WatchHistoryPageResult,
  WatchStatisticsResponseSchema,
  WatchProgressUpdateSchema,
  WatchHistoryUpdateRequestSchema,
  DeleteWatchHistoriesResponse,
} from "@/types/watch_history";

type SortKey = "last_watched" | "progress" | "watch_count" | "total_watch_time";
type SortOrder = "asc" | "desc";

function toMessage(e: unknown): string {
  if (e instanceof Error) return e.message;
  if (typeof e === "string") return e;
  try { return JSON.stringify(e); } catch { return String(e); }
}

export const useWatchHistoryStore = defineStore("watchHistory", () => {
  // 规范化与列表
  const entities = ref<Record<string, WatchHistoryRead>>({});
  const list = ref<WatchHistoryRead[]>([]);
  const listMeta = ref({ total: 0, page: 1, size: 24, pages: 0 });

  // 过滤参数（与后端一致）
  const filters = ref<{ page: number; size: number; watch_type?: WatchType; completed?: boolean }>({
    page: 1,
    size: 24,
    watch_type: undefined,
    completed: undefined,
  });

  // 排序控制
  const sortKey = ref<SortKey>("last_watched");
  const sortOrder = ref<SortOrder>("desc");

  // 最近记录与统计
  const recent = ref<WatchHistoryRead[]>([]);
  const stats = ref<WatchStatisticsResponseSchema | null>(null);

  // ping 状态
  const pingStatus = ref<{ status: string; router: string } | null>(null);

  // 通用状态
  const loading = ref(false);
  const error = ref<string | null>(null);

  // 进度百分比映射（便于渲染）
  const progressPercentById = computed<Record<string, number>>(() => {
    const out: Record<string, number> = {};
    for (const item of list.value) {
      const denom = item.total_duration || 0;
      const ratio = denom > 0 ? item.last_position / denom : 0;
      out[item.id] = Math.max(0, Math.min(1, ratio));
    }
    return out;
  });

  // 排序后的列表
  const sortedList = computed<WatchHistoryRead[]>(() => {
    const base = [...list.value];
    const key = sortKey.value;
    const order = sortOrder.value;

    const getVal = (i: WatchHistoryRead): number => {
      switch (key) {
        case "last_watched":
          return i.last_watched ? new Date(i.last_watched).getTime() : 0;
        case "progress":
          return (i.total_duration ?? 0) > 0 ? i.last_position / (i.total_duration ?? 1) : 0;
        case "watch_count":
          return i.watch_count ?? 0;
        case "total_watch_time":
          return i.total_watch_time ?? 0;
      }
    };

    base.sort((a, b) => {
      const va = getVal(a);
      const vb = getVal(b);
      return order === "asc" ? va - vb : vb - va;
    });
    return base;
  });

  const randomItem = computed<WatchHistoryRead | null>(() => {
    const arr = sortedList.value;
    if (!arr.length) return null;
    const idx = Math.floor(Math.random() * arr.length);
    return arr[idx] ?? null;
  });

  function upsertEntity(item: WatchHistoryRead) {
    entities.value[item.id] = item;
  }

  function upsertEntities(items: WatchHistoryRead[]) {
    for (const it of items) upsertEntity(it);
  }

  // 设置排序
  function setSort(key: SortKey, order: SortOrder = "desc") {
    sortKey.value = key;
    sortOrder.value = order;
  }

  // 设置过滤
  function setWatchType(type?: WatchType) {
    filters.value.watch_type = type;
  }
  function setPage(page: number) {
    filters.value.page = Math.max(1, page);
  }
  function setSize(size: number) {
    filters.value.size = Math.max(1, size);
  }

  // Router ping
  async function ping(options?: { baseURL?: string; signal?: AbortSignal }) {
    try {
      const res = await player.ping(options);
      pingStatus.value = res;
      return res;
    } catch (e) {
      // ping 不影响页面主流程，不设置 error
      throw e;
    }
  }

  // 拉取播放记录列表
  async function fetchList(
    token: string,
    partial?: Partial<{ page: number; size: number; watch_type?: WatchType; completed?: boolean }>,
    options?: { baseURL?: string; signal?: AbortSignal }
  ): Promise<WatchHistoryPageResult> {
    loading.value = true; error.value = null;
    try {
      const params = { ...filters.value, ...(partial ?? {}) };
      const res = await player.listWatchHistories(token, params, options);
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
      error.value = toMessage(e);
      throw e;
    } finally {
      loading.value = false;
    }
  }

  // 最近记录
  async function fetchRecent(
    token: string,
    limit?: number,
    options?: { baseURL?: string; signal?: AbortSignal }
  ): Promise<WatchHistoryRead[]> {
    loading.value = true; error.value = null;
    try {
      const res = await player.getRecentRecords(token, limit, options);
      recent.value = res ?? [];
      upsertEntities(recent.value);
      return recent.value;
    } catch (e) {
      error.value = toMessage(e);
      throw e;
    } finally {
      loading.value = false;
    }
  }

  // 观看统计
  async function fetchStats(
    token: string,
    options?: { baseURL?: string; signal?: AbortSignal }
  ): Promise<WatchStatisticsResponseSchema> {
    loading.value = true; error.value = null;
    try {
      const res = await player.getWatchStatistics(token, options);
      stats.value = res;
      return res;
    } catch (e) {
      error.value = toMessage(e);
      throw e;
    } finally {
      loading.value = false;
    }
  }

  // 更新播放进度
  async function updateProgress(
    token: string,
    payload: WatchProgressUpdateSchema,
    options?: { baseURL?: string; signal?: AbortSignal }
  ): Promise<WatchHistoryRead> {
    loading.value = true; error.value = null;
    try {
      // 通过 payload 信息在本地状态中查找对应记录的 id
      const pickId = (): string | null => {
        // 优先在 recent 中查找
        const byRecent = recent.value.find(i =>
          (payload.movie_id ? i.movie_id === payload.movie_id : true) &&
          (payload.asset_id ? i.asset_id === payload.asset_id : true) &&
          i.type === payload.type
        );
        if (byRecent) return byRecent.id;

        // 其次在当前列表中查找
        const byList = list.value.find(i =>
          (payload.movie_id ? i.movie_id === payload.movie_id : true) &&
          (payload.asset_id ? i.asset_id === payload.asset_id : true) &&
          i.type === payload.type
        );
        if (byList) return byList.id;

        // 最后在 entities 中查找
        for (const it of Object.values(entities.value)) {
          if (
            (payload.movie_id ? it.movie_id === payload.movie_id : true) &&
            (payload.asset_id ? it.asset_id === payload.asset_id : true) &&
            it.type === payload.type
          ) return it.id;
        }
        return null;
      };

      let id = pickId();
      if (!id) {
        // 尝试刷新最近记录后再次查找
        try { await fetchRecent(token, undefined, options); } catch {}
        id = pickId();
      }
      if (!id) {
        throw new Error("未找到对应的观看记录，无法上报进度");
      }
      const updateData: Omit<WatchHistoryUpdateRequestSchema, "id"> = {
        last_position: payload.last_position,
        total_watch_time: undefined,
        last_watched: undefined,
        watch_count: undefined,
        subtitle_enabled: payload.subtitle_enabled,
        subtitle_id: payload.subtitle_id,
        subtitle_sync_data: payload.subtitle_sync_data,
        playback_rate: payload.playback_rate,
        device_info: payload.device_info,
      };

      const res = await player.updateWatchHistoryById(token, id, updateData, options);
      upsertEntity(res);
      const idx = list.value.findIndex(i => i.id === res.id);
      if (idx >= 0) list.value.splice(idx, 1, res);
      return res;
    } catch (e) {
      error.value = toMessage(e);
      throw e;
    } finally {
      loading.value = false;
    }
  }

  // 删除播放记录（支持按 movie_id；不传则清空）
  async function remove(
    token: string,
    movieId?: string | null,
    options?: { baseURL?: string; signal?: AbortSignal }
  ): Promise<DeleteWatchHistoriesResponse> {
    loading.value = true; error.value = null;
    try {
      // 映射为 id 列表：当传入 movieId 时，取当前列表中该电影的所有记录 id；否则传 null/undefined 删除全部
      let ids: string[] | null | undefined;
      if (movieId) {
        const candidates = list.value.filter(i => i.movie_id === movieId).map(i => i.id);
        ids = candidates.length ? candidates : [];
      } else {
        ids = null;
      }

      const res = await player.deleteWatchHistory(token, ids, options);

      if (ids && ids.length) {
        const idSet = new Set(ids);
        list.value = list.value.filter(i => !idSet.has(i.id));
        for (const id of ids) delete entities.value[id];
        listMeta.value.total = Math.max(0, listMeta.value.total - res.deleted);
      } else {
        for (const item of list.value) delete entities.value[item.id];
        list.value = [];
        recent.value = [];
        listMeta.value = { ...listMeta.value, total: 0, pages: 0 };
      }
      return res;
    } catch (e) {
      error.value = toMessage(e);
      throw e;
    } finally {
      loading.value = false;
    }
  }

  // 删除记录
  async function deleteItems(token: string, ids: string[]) {
    loading.value = true;
    try {
      await player.deleteWatchHistory(token, ids);
      // Remove from list locally
      list.value = list.value.filter(i => !ids.includes(i.id));
      recent.value = recent.value.filter(i => !ids.includes(i.id));
      listMeta.value.total = Math.max(0, listMeta.value.total - ids.length);
      for (const id of ids) {
        if (entities.value[id]) delete entities.value[id];
      }
    } catch (e) {
      error.value = toMessage(e);
      throw e;
    } finally {
      loading.value = false;
    }
  }

  return {
    entities,
    list,
    listMeta,
    filters,
    sortKey,
    sortOrder,
    recent,
    stats,
    pingStatus,
    loading,
    error,
    progressPercentById,
    sortedList,
    randomItem,
    upsertEntity,
    upsertEntities,
    setSort,
    setWatchType,
    setPage,
    setSize,
    ping,
    fetchList,
    fetchRecent,
    fetchStats,
    updateProgress,
    remove,
    deleteItems,
  };
});