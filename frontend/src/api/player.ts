import { http } from "./http";
import type {
  WatchType,
  WatchHistoryPageResult,
  WatchHistoryRead,
  WatchHistoryUpdateRequestSchema,
  WatchStatisticsResponseSchema,
  DeleteWatchHistoriesResponse,
  WatchHistoryCreateRequestSchema,
} from "@/types/watch_history";

/**
 * Ping：GET /api/v1/player/ping
 */
export async function ping(
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<{ status: string; router: string }> {
  return http.get<{ status: string; router: string }>("/api/v1/player/ping", {
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 列表：GET /api/v1/player/watch-histories
 */
export async function listWatchHistories(
  token: string,
  params: { page?: number; size?: number; watch_type?: WatchType; completed?: boolean },
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<WatchHistoryPageResult> {
  const qp = new URLSearchParams();
  if (params.page !== undefined) qp.set("page", String(params.page));
  if (params.size !== undefined) qp.set("size", String(params.size));
  if (params.watch_type !== undefined && params.watch_type !== null) {
    qp.set("watch_type", params.watch_type as unknown as string);
  }
  if (params.completed !== undefined && params.completed !== null) {
    qp.set("completed", String(params.completed));
  }

  return http.get<WatchHistoryPageResult>("/api/v1/player/watch-histories", {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
    query: qp,
  });
}

export async function updateWatchHistoryById(
  token: string,
  id: string,
  data: Omit<WatchHistoryUpdateRequestSchema, "id">,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<WatchHistoryRead> {
  return http.patch<WatchHistoryRead>(`/api/v1/player/watch-histories/${id}`,
    data,
    { token, baseURL: options?.baseURL, signal: options?.signal }
  );
}

/**
 * 观看统计：GET /api/v1/player/watch-histories/stats
 */
export async function getWatchStatistics(
  token: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<WatchStatisticsResponseSchema> {
  return http.get<WatchStatisticsResponseSchema>("/api/v1/player/watch-histories/stats", {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 最近记录：GET /api/v1/player/watch-histories/recent
 */
export async function getRecentRecords(
  token: string,
  limit?: number,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<WatchHistoryRead[]> {
  const qp = new URLSearchParams();
  if (limit !== undefined && limit !== null) qp.set("limit", String(limit));

  return http.get<WatchHistoryRead[]>("/api/v1/player/watch-histories/recent", {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
    query: qp,
  });
}

/**
 * 删除记录：DELETE /api/v1/player/watch-histories
 */
export async function deleteWatchHistory(
  token: string,
  ids?: string[] | null,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<DeleteWatchHistoriesResponse> {
  // Backend expects a raw list of strings as the body, not a wrapped object
  // "Input should be a valid list" error indicates it wants [ "id1", "id2" ]
  const body = ids === undefined ? undefined : ids;
  return http.deleteWithBody<DeleteWatchHistoriesResponse>("/api/v1/player/watch-histories", body, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

export async function createWatchHistory(
  token: string,
  data: WatchHistoryCreateRequestSchema,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<WatchHistoryRead> {
  return http.post<WatchHistoryRead>("/api/v1/player/watch-histories", data, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

export async function getWatchHistoryByAsset(
  token: string,
  assetId: string,
  assetType: WatchType,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<WatchHistoryRead | null> {
  const qp = new URLSearchParams();
  qp.set("asset_id", assetId);
  qp.set("asset_type", assetType as unknown as string);
  return http.get<WatchHistoryRead | null>("/api/v1/player/watch-histories/by-asset", {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
    query: qp,
  });
}

export async function getWatchHistoryById(
  token: string,
  id: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<WatchHistoryRead> {
  return http.get<WatchHistoryRead>(`/api/v1/player/watch-histories/${id}`,
    { token, baseURL: options?.baseURL, signal: options?.signal }
  );
}