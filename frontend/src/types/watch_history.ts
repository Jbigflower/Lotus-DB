export enum WatchType {
  Official = "Official",
  Community = "Community",
}

export interface WatchHistoryBase {
  user_id: string;
  asset_id: string;
  movie_id?: string | null;
  type: WatchType;

  last_position: number;
  total_duration: number;
  subtitle_enabled: boolean;
  subtitle_id?: string | null;
  subtitle_sync_data?: number | null;
  playback_rate: number;
  last_watched?: string | null;
  watch_count: number;
  total_watch_time: number;
  device_info: Record<string, string>;
}

export type WatchHistoryCreate = WatchHistoryBase;

export interface WatchHistoryUpdate {
  last_position?: number | null;
  total_duration?: number | null;
  total_watch_time?: number | null;
  last_watched?: string | null;
  watch_count?: number | null;
  subtitle_enabled?: boolean | null;
  subtitle_id?: string | null;
  subtitle_sync_data?: number | null;
  playback_rate?: number | null;
  device_info?: Record<string, string> | null;
}

export interface WatchHistoryInDB extends WatchHistoryBase {
  id: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export type WatchHistoryRead = WatchHistoryInDB;

export interface WatchHistoryPageResult {
  items: WatchHistoryRead[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

/**
 * 路由层 Schema（请求/响应），与后端保持同名字段
 */
export interface WatchHistoryCreateRequestSchema extends Omit<WatchHistoryCreate, "user_id"> {
  user_id?: string | null;
}

export interface WatchHistoryUpdateRequestSchema extends WatchHistoryUpdate {
  id: string;
}

export type WatchHistoryReadResponseSchema = WatchHistoryRead;

export type WatchHistoryPageResultResponseSchema = WatchHistoryPageResult;

export interface WatchProgressUpdateSchema {
  movie_id: string;
  asset_id?: string | null;
  type: WatchType;
  last_position: number;
  total_duration?: number | null;
  device_info?: Record<string, string> | null;
  subtitle_enabled?: boolean | null;
  subtitle_id?: string | null;
  subtitle_sync_data?: number | null;
  playback_rate?: number | null;
}

export interface WatchStatisticsResponseSchema {
  total_movies: number;
  total_watch_time: number;
  total_watch_count: number;
  avg_progress: number;
}

export interface DeleteWatchHistoriesResponse {
  deleted: number;
  message: string;
  ok: boolean;
}