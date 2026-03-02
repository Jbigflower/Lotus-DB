import { http, resolveBaseURL, resolveMediaURL } from "./http";
import { AssetStoreType } from "@/types/user_asset";
import type {
  UserAssetType,
  UserAssetRead,
  UserAssetUpdateRequestSchema,
  UserAssetPageResult,
  PartialPageResult,
} from "@/types/user_asset";

// Ping：GET /api/v1/user_assets/ping
export async function ping(
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<{ status: string; router: string }> {
  return http.get<{ status: string; router: string }>("/api/v1/user_assets/ping", {
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

// 列表查询：GET /api/v1/user_assets/
export interface ListUserAssetsParams {
  q?: string;
  movie_ids?: string[]; // 后端改为数组参数
  asset_type?: UserAssetType[];
  tags?: string[];
  is_public?: boolean;
  is_deleted?: boolean;
  page?: number;
  size?: number;
}

export type ListUserAssetsResponse =
  | UserAssetPageResult
  | PartialPageResult<UserAssetRead>; // 直接返回分页结果，不再包 status/result

export async function listUserAssets(
  token: string,
  params: ListUserAssetsParams = {},
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<ListUserAssetsResponse> {
  const qp = new URLSearchParams();
  if (params.q) qp.set("q", params.q);
  if (params.movie_ids) {
    for (const id of params.movie_ids) qp.append("movie_ids", id);
  }
  if (params.asset_type) {
    for (const t of params.asset_type) qp.append("asset_type", t as unknown as string);
  }
  if (params.tags) {
    for (const tag of params.tags) qp.append("tags", tag);
  }
  if (params.is_public !== undefined) qp.set("is_public", String(params.is_public));
  if (params.is_deleted !== undefined) qp.set("is_deleted", String(params.is_deleted));
  if (params.page !== undefined) qp.set("page", String(params.page));
  if (params.size !== undefined) qp.set("size", String(params.size));

  return http.get<ListUserAssetsResponse>("/api/v1/user_assets/", {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
    query: qp,
  });
}

// 详情：GET /api/v1/user_assets/{asset_id}
export async function getUserAsset(
  token: string,
  assetId: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<UserAssetRead> {
  return http.get<UserAssetRead>(`/api/v1/user_assets/${assetId}`, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

// 上传（文件/本地路径）：POST /api/v1/user_assets/upload
export interface UploadUserAssetForm {
  file?: File | Blob;
  local_path?: string;
  movie_id: string;
  type: UserAssetType;
  store_type?: AssetStoreType;
  name?: string | null;
  is_public?: boolean;
  tags?: string[] | null;
  related_movie_ids?: string[] | null;
  content?: string | null;
}

export async function uploadUserAsset(
  token: string,
  form: UploadUserAssetForm,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<{ asset: UserAssetRead; tasks: Record<string, unknown> }> {
  const fd = new FormData();
  if (form.file) fd.append("file", form.file);
  if (form.local_path) fd.append("local_path", form.local_path);

  fd.set("movie_id", form.movie_id);
  fd.set("type", form.type as unknown as string);
  fd.set("store_type", (form.store_type ?? "local") as unknown as string);
  if (form.name !== undefined && form.name !== null) fd.set("name", form.name);
  if (form.is_public !== undefined) fd.set("is_public", String(form.is_public));
  if (form.tags) for (const tag of form.tags) fd.append("tags", tag);
  if (form.related_movie_ids)
    for (const id of form.related_movie_ids) fd.append("related_movie_ids", id);
  if (form.content !== undefined && form.content !== null) fd.set("content", form.content);

  return http.post<{ asset: UserAssetRead; tasks: Record<string, unknown> }>(
    "/api/v1/user_assets/upload",
    fd,
    {
      token,
      baseURL: options?.baseURL,
      signal: options?.signal,
    }
  );
}

// 文本创建：POST /api/v1/user_assets/text
export async function createTextUserAsset(
  token: string,
  body: {
    movie_id: string;
    type: UserAssetType; // 仅 NOTE/REVIEW
    name?: string | null;
    is_public?: boolean;
    tags?: string[] | null;
    related_movie_ids?: string[] | null;
    content: string;
    store_type?: AssetStoreType | null;
  },
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<UserAssetRead> {
  const payload = { ...body, store_type: body.store_type ?? AssetStoreType.LOCAL } as any
  return http.post<UserAssetRead>(`/api/v1/user_assets/text`, payload, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

// 生成截图：POST /api/v1/user_assets/screenshot

// 单资产更新：PATCH /api/v1/user_assets/{asset_id}
export type UpdateUserAssetResponse = UserAssetRead;

export async function updateUserAsset(
  token: string,
  assetId: string,
  patch: UserAssetUpdateRequestSchema,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<UserAssetRead> {
  return http.patch<UserAssetRead>(`/api/v1/user_assets/${assetId}`, patch, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

// 批量更新：PATCH /api/v1/user_assets/
export async function updateUserAssetsBatch(
  token: string,
  assetIds: string[],
  patch: UserAssetUpdateRequestSchema,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<UserAssetRead[]> {
  // 优先尝试后端批量更新端点（若后端暂未提供，则降级为逐个 PATCH）
  const body = { asset_ids: assetIds, patch };
  try {
    return await http.patch<UserAssetRead[]>(`/api/v1/user_assets/`, body, {
      token,
      baseURL: options?.baseURL,
      signal: options?.signal,
    });
  } catch (e: any) {
    const status = (e && typeof e === "object" && "status" in e) ? (e as any).status : undefined;
    if (status !== 404 && status !== 405) throw e; // 非端点缺失错误则抛出
    // 端点缺失：逐个调用单资源更新
    const promises = assetIds.map((id) =>
      http.patch<UserAssetRead>(`/api/v1/user_assets/${id}`, patch, {
        token,
        baseURL: options?.baseURL,
        signal: options?.signal,
      })
    );
    return Promise.all(promises);
  }
}

// 单资产删除：DELETE /api/v1/user_assets/{asset_id}
export async function deleteUserAsset(
  token: string,
  assetId: string,
  softDelete = true,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<{ message: string; success: number; failed: number }> {
  const qp = new URLSearchParams();
  qp.set("soft_delete", String(softDelete));
  return http.delete<{ message: string; success: number; failed: number }>(
    `/api/v1/user_assets/${assetId}`,
    {
      token,
      baseURL: options?.baseURL,
      signal: options?.signal,
      query: qp,
    }
  );
}

// 批量删除：DELETE /api/v1/user_assets/
export async function deleteUserAssetsBatch(
  token: string,
  assetIds: string[],
  softDelete = true,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<{ message: string; success: number; failed: number }> {
  const body = { asset_ids: assetIds };
  const qp = new URLSearchParams();
  qp.set("soft_delete", String(softDelete));
  return http.deleteWithBody<{ message: string; success: number; failed: number }>(
    `/api/v1/user_assets/`,
    body,
    {
      token,
      baseURL: options?.baseURL,
      signal: options?.signal,
      query: qp,
    }
  );
}

export async function restoreUserAssets(
  token: string,
  assetIds: string[],
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<UserAssetRead[]> {
  const body = { asset_ids: assetIds };
  return http.post<UserAssetRead[]>("/api/v1/user_assets/restore", body, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

// 批量设置公开状态：PATCH /api/v1/user_assets/active_status
export async function setUserAssetsActiveStatus(
  token: string,
  assetIds: string[],
  isPublic: boolean,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<UserAssetRead[]> {
  const body = { asset_ids: assetIds, is_public: isPublic };
  return http.patch<UserAssetRead[]>(`/api/v1/user_assets/active_status`, body, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

// 孤立资产列表：GET /api/v1/user_assets/isolated
export async function listIsolatedAssets(
  token: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<UserAssetRead[]> {
  return http.get<UserAssetRead[]>(`/api/v1/user_assets/isolated`, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

// 资产分配：POST /api/v1/user_assets/allocate
export async function allocateAssets(
  token: string,
  allocateMap: Record<string, string[]>,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<UserAssetRead[]> {
  const body = { allocate_map: allocateMap };
  return http.post<UserAssetRead[]>(`/api/v1/user_assets/allocate`, body, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

// 新增：批量缩略图签名
export async function getUserAssetThumbnailsSigned(
  token: string,
  assetIds: string[],
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<string[]> {
  const body = { asset_ids: assetIds };
  return http.post<string[]>(`/api/v1/user_assets/thumbnails/sign`, body, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

// 构造用户资产文件下载/播放 URL：GET /api/v1/user_assets/{asset_id}/file
// 用于 <video src> 或 <img src>，不直接发起请求
export function buildUserAssetFileURL(
  assetId: string,
  params?: {
    transcode?: boolean;
    start?: number;
    duration?: number;
    target_bitrate_kbps?: number;
    target_resolution?: string;
  },
  baseURL?: string
): string {
  const qp = new URLSearchParams();
  if (params?.transcode != null) qp.set("transcode", String(params.transcode));
  if (params?.start != null) qp.set("start", String(params.start));
  if (params?.duration != null) qp.set("duration", String(params.duration));
  if (params?.target_bitrate_kbps != null)
    qp.set("target_bitrate_kbps", String(params.target_bitrate_kbps));
  if (params?.target_resolution) qp.set("target_resolution", params.target_resolution);
  const base = resolveMediaURL(baseURL);
  const qs = qp.toString();
  const path = `/api/v1/user_assets/${assetId}/file${qs ? `?${qs}` : ""}`;
  return `${base}${path}`;
}

export async function getUserAssetFile(
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
  if (params?.target_bitrate_kbps !== undefined)
    qp.set("target_bitrate_kbps", String(params.target_bitrate_kbps));
  if (params?.target_resolution) qp.set("target_resolution", params.target_resolution);
  return http.get<string>(`/api/v1/user_assets/${assetId}/file`, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
    query: qp,
  });
}


// // 获取用户资产文件（签名URL）：GET /api/v1/user_assets/{asset_id}/file
// // 支持参数：transcode, start, duration, target_bitrate_kbps
// export async function getUserAssetFile(
//   token: string,
//   assetId: string,
//   params: {
//     transcode?: boolean;
//     start?: number;
//     duration?: number;
//     target_bitrate_kbps?: number;
//   } = {},
//   options?: { baseURL?: string; signal?: AbortSignal }
// ): Promise<string> {
//   const qp = new URLSearchParams();
//   if (params.transcode) qp.set("transcode", "true");
//   if (params.start !== undefined) qp.set("start", String(params.start));
//   if (params.duration !== undefined) qp.set("duration", String(params.duration));
//   if (params.target_bitrate_kbps !== undefined) qp.set("target_bitrate_kbps", String(params.target_bitrate_kbps));

//   return http.get<string>(`/api/v1/user_assets/${assetId}/file`, {
//     token,
//     baseURL: options?.baseURL,
//     signal: options?.signal,
//     query: qp,
//   });
// }