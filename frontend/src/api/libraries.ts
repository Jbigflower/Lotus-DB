// 媒体库模块 API：与后端 /api/v1/libraries 路由对齐
import { http } from "./http";
import type {
  LibraryType,
  LibraryRead,
  LibraryPageResult,
  LibraryCreateRequestSchema,
  LibraryUpdateRequestSchema,
} from "../types/library";


export interface ListLibrariesParams {
  page?: number;
  page_size?: number;
  library_type: LibraryType; // 必填，后端参数名为 library_type
  is_active?: boolean;
  is_deleted?: boolean;
  auto_import?: boolean | null;
  query?: string;
  only_me?: boolean;
}


/**
 * 列举出所有的库：GET /api/v1/libraries/
 */
export async function listLibraries(
  token: string,
  params: ListLibrariesParams,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<LibraryPageResult> {
  const qp = new URLSearchParams();
  if (params.page !== undefined) qp.set("page", String(params.page));
  if (params.page_size !== undefined) qp.set("page_size", String(params.page_size));
  qp.set("library_type", params.library_type);
  if (params.is_active !== undefined) qp.set("is_active", String(params.is_active));
  if (params.is_deleted !== undefined) qp.set("is_deleted", String(params.is_deleted));
  if (params.auto_import !== undefined && params.auto_import !== null) {
    qp.set("auto_import", String(params.auto_import));
  }
  if (params.query !== undefined) qp.set("query", params.query);
  if (params.only_me !== undefined) qp.set("only_me", String(params.only_me));

  return http.get<LibraryPageResult>("/api/v1/libraries/", {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
    query: qp,
  });
}

/**
 * 获取指定库详情：GET /api/v1/libraries/{library_id}
 */
export async function getLibrary(
  token: string,
  libraryId: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<LibraryRead> {
  return http.get<LibraryRead>(`/api/v1/libraries/${libraryId}`, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 创建一个新的库：POST /api/v1/libraries/
 */
export async function createLibrary(
  token: string,
  payload: LibraryCreateRequestSchema,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<LibraryRead> {
  return http.post<LibraryRead>("/api/v1/libraries/", payload, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 修改库配置：PATCH /api/v1/libraries/{library_id}
 */
export async function updateLibrary(
  token: string,
  libraryId: string,
  payload: LibraryUpdateRequestSchema,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<LibraryRead> {
  return http.patch<LibraryRead>(`/api/v1/libraries/${libraryId}`, payload, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 激活 or 停用库：PATCH /api/v1/libraries/{library_id}/active
 * Body 为 JSON 布尔值
 */
export async function setLibraryActive(
  token: string,
  libraryId: string,
  isActive: boolean,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<LibraryRead> {
  return http.patch<LibraryRead>(`/api/v1/libraries/${libraryId}/active`, isActive, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 公开 or 私有库：PATCH /api/v1/libraries/{library_id}/public
 * Body 为 JSON 布尔值
 */
export async function setLibraryPublic(
  token: string,
  libraryId: string,
  isPublic: boolean,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<LibraryRead> {
  return http.patch<LibraryRead>(`/api/v1/libraries/${libraryId}/public`, isPublic, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 删除库：DELETE /api/v1/libraries/{library_id}?soft_delete=
 */
export async function deleteLibrary(
  token: string,
  libraryId: string,
  softDelete = false,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<Record<string, unknown>> {
  const qp = new URLSearchParams();
  qp.set("soft_delete", String(softDelete));

  return http.delete<Record<string, unknown>>(`/api/v1/libraries/${libraryId}`, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
    query: qp,
  });
}

/**
 * 恢复库：PATCH /api/v1/libraries/{library_id}/restore
 */
export async function restoreLibrary(
  token: string,
  libraryId: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<LibraryRead> {
  // 后端路由调整为 POST /api/v1/libraries/restore，Body 为 JSON 字符串 library_id
  return http.post<LibraryRead>("/api/v1/libraries/restore", libraryId, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 主动触发扫描：POST /api/v1/libraries/{library_id}/scan
 */
export async function scanLibrary(
  token: string,
  libraryId: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<Record<string, unknown>> {
  return http.post<Record<string, unknown>>(`/api/v1/libraries/${libraryId}/scan`, undefined, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 获取库的统计信息：GET /api/v1/libraries/{library_id}/stats
 */
export async function getLibraryStats(
  token: string,
  libraryId: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<Record<string, unknown>> {
  return http.get<Record<string, unknown>>(`/api/v1/libraries/${libraryId}/stats`, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 进入库：POST /api/v1/libraries/{library_id}/enter
 */
export async function enterLibrary(
  token: string,
  libraryId: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<LibraryRead> {
  return http.post<LibraryRead>(`/api/v1/libraries/${libraryId}/enter`, undefined, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 退出库：POST /api/v1/libraries/exit
 */
export async function exitLibrary(
  token: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<Record<string, string>> {
  return http.post<Record<string, string>>(`/api/v1/libraries/exit`, undefined, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 获取当前库：GET /api/v1/libraries/current
 */
export async function getCurrentLibrary(
  token: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<LibraryRead | null> {
  return http.get<LibraryRead | null>(`/api/v1/libraries/current`, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

export async function getLibraryCoversSigned(
  token: string,
  ids: string[],
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<string[]> {
  return http.post<string[]>("/api/v1/libraries/covers/sign", ids, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

export async function uploadLibraryCover(
  token: string,
  libraryId: string,
  file: File,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<Record<string, unknown>> {
  const formData = new FormData();
  formData.append("file", file);

  return http.post<Record<string, unknown>>(`/api/v1/libraries/${libraryId}/cover`, formData, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}
