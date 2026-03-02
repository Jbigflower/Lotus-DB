import { http, resolveBaseURL, resolveMediaURL } from "./http";
import type {
  AssetType,
  AssetRead,
  AssetPageResult,
  AssetUpdateRequestSchema,
} from "../types/asset";

/**
 * 全局资产列表：GET /assets
 */
export async function getGlobalAssets(
  token: string,
  params: { page?: number; size?: number } = {},
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<AssetPageResult> {
  const qp = new URLSearchParams();
  if (params.page !== undefined) qp.set("page", String(params.page));
  if (params.size !== undefined) qp.set("size", String(params.size));
  return http.get<AssetPageResult>("/assets/", {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
    query: qp,
  });
}

/**
 * 资产列表：GET /assets/movies/{movie_id}
 */
export async function getMovieAssets(
  token: string,
  movieId: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<AssetPageResult> {
  return http.get<AssetPageResult>(`/assets/movies/${movieId}`, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 回收站列表：GET /assets/recycle-bin
 */
export async function listRecycleBinAssets(
  token: string,
  params: { page?: number; size?: number } = {},
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<AssetPageResult> {
  const qp = new URLSearchParams();
  if (params.page !== undefined) qp.set("page", String(params.page));
  if (params.size !== undefined) qp.set("size", String(params.size));
  return http.get<AssetPageResult>("/assets/recycle-bin", {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
    query: qp,
  });
}

/**
 * 通过 URL 导入资产：POST /assets/{movie_id}
 * FormData: type, url, name?
 * 返回响应字典中的 asset 字段
 */
export async function importMovieAssetFromUrl(
  token: string,
  movieId: string,
  libraryId: string,
  params: { type: AssetType; url: string; name?: string | null },
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<AssetRead> {
  const form = new FormData();
  form.append("type", params.type as unknown as string);
  form.append("url", params.url);
  if (params.name) form.append("name", params.name);
  form.append("library_id", libraryId);
  const res = await http.post<{ asset: AssetRead; tasks: unknown }>(`/assets/${movieId}`, form, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
  return res.asset;
}

/**
 * 上传资产文件：POST /assets/{movie_id}
 * FormData: type, name?, file
 * 返回响应字典中的 asset 字段
 */
export async function uploadMovieAssetFile(
  token: string,
  movieId: string,
  libraryId: string,
  params: { type: AssetType; name?: string | null },
  file: File | Blob,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<AssetRead> {
  const form = new FormData();
  form.append("type", params.type as unknown as string);
  if (params.name) form.append("name", params.name);
  form.append("file", file);
  form.append("library_id", libraryId);
  const res = await http.post<{ asset: AssetRead; tasks: unknown }>(`/assets/${movieId}`, form, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
  return res.asset;
}

/**
 * 服务端本地路径复制上传：POST /assets/{movie_id}
 * FormData: type, name?, local_path
 * 返回响应字典中的 asset 字段
 */
export async function importMovieAssetFromLocal(
  token: string,
  movieId: string,
  libraryId: string,
  params: { type: AssetType; src_path: string; name?: string | null },
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<AssetRead> {
  const form = new FormData();
  form.append("type", params.type as unknown as string);
  form.append("local_path", params.src_path);
  if (params.name) form.append("name", params.name);
  form.append("library_id", libraryId);
  const res = await http.post<{ asset: AssetRead; tasks: unknown }>(`/assets/${movieId}`, form, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
  return res.asset;
}

/**
 * 更新资产：PATCH /assets/{asset_id}
 */
export async function updateMovieAsset(
  token: string,
  movieId: string,
  assetId: string,
  patch: AssetUpdateRequestSchema,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<AssetRead> {
  return http.patch<AssetRead>(`/assets/${assetId}`, patch, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 删除资产：DELETE /assets/{asset_id}?soft_delete=
 */
export async function deleteMovieAsset(
  token: string,
  movieId: string,
  assetId: string,
  softDelete = true,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<Record<string, unknown>> {
  const qp = new URLSearchParams();
  qp.set("soft_delete", String(softDelete));
  return http.delete<Record<string, unknown>>(`/assets/${assetId}`, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
    query: qp,
  });
}

/**
 * 获取单个资产详情：GET /assets/{asset_id}
 */
export async function getMovieAsset(
  token: string,
  assetId: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<AssetRead> {
  return http.get<AssetRead>(`/assets/${assetId}`, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 获取资产文件签名URL：GET /assets/{asset_id}/file
 * 返回字符串URL，适用于 <video src> 直接使用（无额外请求头）
 */
export async function getMovieAssetFile(
  token: string,
  assetId: string,
  params?: {
    transcode?: boolean;
    start?: number;
    duration?: number;
    target_bitrate_kbps?: number;
    target_resolution?: string;
  },
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<string> {
  const qp = new URLSearchParams();
  if (params?.transcode !== undefined) qp.set("transcode", String(params.transcode));
  if (params?.start !== undefined) qp.set("start", String(params.start));
  if (params?.duration !== undefined) qp.set("duration", String(params.duration));
  if (params?.target_bitrate_kbps !== undefined) qp.set("target_bitrate_kbps", String(params.target_bitrate_kbps));
  if (params?.target_resolution) qp.set("target_resolution", params.target_resolution);
  return http.get<string>(`/assets/${assetId}/file`, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
    query: qp,
  });
}

/**
 * 批量删除资产：DELETE /assets/bulk?soft_delete=
 * Body: { asset_ids: string[] }
 */
export async function deleteMovieAssetsBulk(
  token: string,
  assetIds: string | string[],
  softDelete = true,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<{ message: string; success: number; failed: number }> {
  const idsArray = Array.isArray(assetIds)
    ? assetIds
    : assetIds.split(",").map((s) => s.trim()).filter(Boolean);
  const qp = new URLSearchParams();
  qp.set("soft_delete", String(softDelete));
  const body = { asset_ids: idsArray };
  return http.deleteWithBody<{ message: string; success: number; failed: number }>(
    "/assets/bulk",
    body,
    {
      token,
      baseURL: options?.baseURL,
      signal: options?.signal,
      query: qp,
    }
  );
}

/**
 * 批量恢复资产：POST /assets/restore
 * Body: { asset_ids: string[] }
 */
export async function restoreMovieAssets(
  token: string,
  assetIds: string | string[],
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<AssetRead[]> {
  const idsArray = Array.isArray(assetIds)
    ? assetIds
    : assetIds.split(",").map((s) => s.trim()).filter(Boolean);
  const body = { asset_ids: idsArray };
  return http.post<AssetRead[]>("/assets/restore", body, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 获取资产缩略图签名：POST /assets/thumbnails/sign
 * Body: { asset_ids: string[] }
 * 返回签名 URL 列表
 */
export async function getAssetThumbnailsSigned(
  token: string,
  assetIds: string | string[],
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<string[]> {
  const idsArray = Array.isArray(assetIds)
    ? assetIds
    : assetIds.split(",").map((s) => s.trim()).filter(Boolean);
  const body = { asset_ids: idsArray };
  return http.post<string[]>("/assets/thumbnails/sign", body, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 构造资产文件下载/播放 URL：GET /assets/{asset_id}/file
 * 用于 <video src> 或下载链接，不直接发起请求。
 */
export function buildAssetFileURL(
  assetId: string,
  params?: {
    transcode?: boolean;
    start?: number;
    duration?: number;
    target_bitrate_kbps?: number;
    target_resolution?: string;
  },
  token?: string,
  baseURL?: string
): string {
  const qp = new URLSearchParams();
  if (token) qp.set("token", token);
  if (params?.transcode != null) qp.set("transcode", String(params.transcode));
  if (params?.start != null) qp.set("start", String(params.start));
  if (params?.duration != null) qp.set("duration", String(params.duration));
  if (params?.target_bitrate_kbps != null)
    qp.set("target_bitrate_kbps", String(params.target_bitrate_kbps));
  if (params?.target_resolution) qp.set("target_resolution", params.target_resolution);
  const base = resolveMediaURL(baseURL);
  const qs = qp.toString();
  const path = `/assets/${assetId}/file${qs ? `?${qs}` : ""}`;
  return `${base}${path}`;
}