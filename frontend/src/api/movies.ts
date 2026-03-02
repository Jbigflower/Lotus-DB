// 顶部导入：改为从前端类型文件中进行 type-only 导入
import { http } from "./http";

import type {
  MovieRead,
  MovieCreateRequestSchema,
  MovieUpdateRequestSchema,
  MoviePageResult,
  MovieCreateResponse,
} from "../types/movie";
import type {TaskRead} from "../types/task";


function appendArrayParams(qp: URLSearchParams, key: string, arr?: string[] | null) {
  if (!arr || arr.length === 0) return;
  for (const v of arr) qp.append(key, v);
}

/**
 * 列表查询：GET /api/v1/movies/
 */
export async function listMovies(
  token: string,
  params: {
    library_id?: string | null;
    query?: string | null;
    genres?: string[] | null;
    min_rating?: number | null;
    max_rating?: number | null;
    start_date?: string | null; // YYYY-MM-DD
    end_date?: string | null;   // YYYY-MM-DD
    tags?: string[] | null;
    page?: number;
    size?: number;
    sort_by?: string | null;
    sort_dir?: number | null;   // 1 或 -1
    is_deleted?: boolean;
  },
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<MoviePageResult> {
  const qp = new URLSearchParams();
  if (params.library_id) qp.set("library_id", params.library_id);
  if (params.query) qp.set("query", params.query);
  appendArrayParams(qp, "genres", params.genres ?? undefined);
  if (params.min_rating != null) qp.set("min_rating", String(params.min_rating));
  if (params.max_rating != null) qp.set("max_rating", String(params.max_rating));
  if (params.start_date) qp.set("start_date", params.start_date);
  if (params.end_date) qp.set("end_date", params.end_date);
  appendArrayParams(qp, "tags", params.tags ?? undefined);
  if (params.page != null) qp.set("page", String(params.page));
  if (params.size != null) qp.set("size", String(params.size));
  if (params.sort_by) qp.set("sort_by", params.sort_by);
  if (params.sort_dir != null) qp.set("sort_dir", String(params.sort_dir));
  if (params.is_deleted !== undefined) qp.set("is_deleted", String(params.is_deleted));

  return http.get<MoviePageResult>("/api/v1/movies/", {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
    query: qp,
  });
}

/**
 * 创建电影：POST /api/v1/movies/
 */
export async function createMovie(
  token: string,
  payload: MovieCreateRequestSchema,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<MovieCreateResponse> {
  return http.post<MovieCreateResponse>("/api/v1/movies/", payload, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 最近电影列表：GET /api/v1/movies/recent
 */
export async function listRecentMovies(
  token: string,
  params?: { library_id?: string | null; size?: number },
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<MovieRead[]> {
  const qp = new URLSearchParams();
  if (params?.library_id) qp.set("library_id", params.library_id);
  if (params?.size != null) qp.set("size", String(params.size));
  return http.get<MovieRead[]>("/api/v1/movies/recent", {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
    query: qp,
  });
}

/**
 * 回收站电影列表：GET /api/v1/movies/recycle-bin
 */
export async function listRecycleBinMovies(
  token: string,
  params: {
    page?: number;
    size?: number;
  },
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<MoviePageResult> {
  const qp = new URLSearchParams();
  if (params.page != null) qp.set("page", String(params.page));
  if (params.size != null) qp.set("size", String(params.size));

  return http.get<MoviePageResult>("/api/v1/movies/recycle-bin", {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
    query: qp,
  });
}

/**
 * 获取电影详情：GET /api/v1/movies/{movie_id}
 */
export async function getMovie(
  token: string,
  movieId: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<MovieRead> {
  return http.get<MovieRead>(`/api/v1/movies/${movieId}`, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}


/**
 * 批量获取电影封面签名：POST /api/v1/movies/covers/sign
 * Body: { ids: string[], image?: 'poster.jpg'|'thumbnail.jpg'|'backdrop.jpg'|'all' }
 */
export async function getMovieCoversSigned(
  token: string,
  ids: string[],
  image: "poster.jpg" | "thumbnail.jpg" | "backdrop.jpg" | "all" = "poster.jpg",
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<string[]> {
  const body = { ids, image };
  return http.post<string[]>("/api/v1/movies/covers/sign", body, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 批量导入：POST /api/v1/movies/bulk
 * 上传一个包含电影数据的 JSON 文件，返回 Task
 */
export async function importMoviesBatch(
  token: string,
  file: File | Blob,
  params?: { library_id?: string | null },
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<TaskRead> {
  const form = new FormData();
  form.append("file", file);
  const qp = new URLSearchParams();
  if (params?.library_id) qp.set("library_id", params.library_id);
  return http.post<TaskRead>("/api/v1/movies/bulk", form, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
    query: qp,
  });
}

/**
 * 更新电影-单个：PATCH /api/v1/movies/{movie_id}
 */
export async function updateMovie(
  token: string,
  movieId: string,
  patch: MovieUpdateRequestSchema,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<MovieRead> {
  return http.patch<MovieRead>(`/api/v1/movies/${movieId}`, patch, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 更新电影-批量：PATCH /api/v1/movies/batch
 * Body: { movie_ids: string[], patch: MovieUpdateRequestSchema }
 */
export async function updateMovies(
  token: string,
  movieIds: string | string[],
  patch: MovieUpdateRequestSchema,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<MovieRead[]> {
  const idsArray = Array.isArray(movieIds)
    ? movieIds
    : movieIds.split(",").map(s => s.trim()).filter(Boolean);
  const body = { movie_ids: idsArray, patch };
  return http.patch<MovieRead[]>("/api/v1/movies/batch", body, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 删除电影-批量：DELETE /api/v1/movies/bulk?soft_delete=
 * Body: string[]（movie_ids 列表）
 */
export async function deleteMovies(
  token: string,
  movieIds: string | string[],
  softDelete = false,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<{ message: string; success: number; failed: number }> {
  const idsArray = Array.isArray(movieIds)
    ? movieIds
    : movieIds.split(",").map(s => s.trim()).filter(Boolean);
  const qp = new URLSearchParams();
  qp.set("soft_delete", String(softDelete));
  return http.deleteWithBody<{ message: string; success: number; failed: number }>(
    "/api/v1/movies/bulk",
    idsArray,
    {
      token,
      baseURL: options?.baseURL,
      signal: options?.signal,
      query: qp,
    }
  );
}

/**
 * 恢复电影-批量：POST /api/v1/movies/restore
 * Body: string[]（movie_ids 列表）
 */
export async function restoreMovies(
  token: string,
  movieIds: string | string[],
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<MovieRead[]> {
  const idsArray = Array.isArray(movieIds)
    ? movieIds
    : movieIds.split(",").map(s => s.trim()).filter(Boolean);
  return http.post<MovieRead[]>("/api/v1/movies/restore", idsArray, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

export async function uploadMoviePoster(
  token: string,
  movieId: string,
  file: File | Blob,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<MovieRead> {
  const form = new FormData();
  form.append("file", file);
  return http.post<MovieRead>(`/api/v1/movies/${movieId}/poster`, form, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

export async function uploadMovieImages(
  token: string,
  movieId: string,
  files: Array<File | Blob>,
  types: Array<"poster" | "backdrop">,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<MovieRead> {
  const form = new FormData();
  if (!files || !types || files.length !== types.length) {
    throw new Error("文件与类型数量不匹配");
  }
  for (let i = 0; i < files.length; i++) {
    form.append("files", files[i]);
    form.append("types", types[i]);
  }
  return http.post<MovieRead>(`/api/v1/movies/${movieId}/images`, form, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

export async function scrapeMovieMetadata(
  token: string,
  movieId: string,
  pluginNames?: string[] | null,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<TaskRead> {
  const body = pluginNames ?? [];
  return http.post<TaskRead>(`/api/v1/movies/${movieId}/metadata/scrape`, body, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

export async function scrapeMovieSubtitles(
  token: string,
  movieId: string,
  pluginNames?: string[] | null,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<TaskRead> {
  const body = pluginNames ?? [];
  return http.post<TaskRead>(`/api/v1/movies/${movieId}/subtitles/scrape`, body, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

// 移除以下资产相关方法：
// - getMovieAssets
// - importMovieAssetFromUrl
// - uploadMovieAssetFile
// - importMovieAssetFromLocal
// - updateMovieAsset
// - deleteMovieAsset
