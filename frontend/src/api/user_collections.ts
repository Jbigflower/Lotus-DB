import { http } from "./http";
import {
  CustomListType,
  type CustomListRead,
  type CustomListCreateRequestSchema,
  type CustomListUpdateRequestSchema,
  type CustomListPageResultResponseSchema,
} from "@/types/user_collection";
import type { MovieRead } from "@/types/movie";

/**
 * 前后端 type 值映射：CUSTOMLIST <-> custom
 */
// 前后端 type 值映射：CUSTOMLIST <-> custom
function mapFrontendTypeToBackend(t?: CustomListType | null): string | undefined {
  if (t === CustomListType.CUSTOMLIST) return "customlist";
  if (t === CustomListType.FAVORITE) return "favorite";
  if (t === CustomListType.WATCHLIST) return "watchlist";
  return t as unknown as string | undefined;
}

function mapBackendTypeToFrontend(s: string): CustomListType {
  switch (s) {
    case "customlist":
    case "custom": // 兼容旧值
      return CustomListType.CUSTOMLIST;
    case "favorite":
      return CustomListType.FAVORITE;
    case "watchlist":
      return CustomListType.WATCHLIST;
    default:
      return s as unknown as CustomListType;
  }
}

function mapReadFromBackend(r: any): CustomListRead {
  return {
    ...r,
    type: mapBackendTypeToFrontend(r?.type),
  };
}

/**
 * 列举当前用户的片单：GET /api/v1/user_collections/?type=...
 * 返回分页结果 CustomListPageResultResponseSchema
 */
export async function listUserCollections(
  token: string,
  type?: CustomListType,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<CustomListPageResultResponseSchema> {
  const qp = new URLSearchParams();
  if (type !== undefined && type !== null) {
    const t = mapFrontendTypeToBackend(type);
    if (t) qp.set("type", t);
  }
  const res = await http.get<CustomListPageResultResponseSchema>("/api/v1/user_collections/", {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
    query: qp,
  });
  return {
    ...res,
    items: res.items.map(mapReadFromBackend),
  };
}

/**
 * 获取片单详情：GET /api/v1/user_collections/{collection_id}
 */
export async function getUserCollection(
  token: string,
  collectionId: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<CustomListRead> {
  const res = await http.get<CustomListRead>(`/api/v1/user_collections/${collectionId}`, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
  return mapReadFromBackend(res);
}

/**
 * 创建片单：POST /api/v1/user_collections/
 */
export async function createUserCollection(
  token: string,
  payload: CustomListCreateRequestSchema,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<CustomListRead> {
  const payloadForBackend = {
    ...payload,
    type: payload?.type ? mapFrontendTypeToBackend(payload.type) : payload?.type,
  };
  const res = await http.post<CustomListRead>("/api/v1/user_collections/", payloadForBackend, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
  return mapReadFromBackend(res);
}

/**
 * 更新片单：PATCH /api/v1/user_collections/{collection_id}
 * 注意：后端 CollectionUpdateSchema 仅强约束 name，其他字段取自 CustomListUpdate
 */
export async function updateUserCollection(
  token: string,
  collectionId: string,
  patch: CustomListUpdateRequestSchema,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<CustomListRead> {
  const patchForBackend = {
    ...patch,
  };
  const res = await http.patch<CustomListRead>(`/api/v1/user_collections/${collectionId}`, patchForBackend, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
  return mapReadFromBackend(res);
}

/**
 * 删除片单：DELETE /api/v1/user_collections/{collection_id}
 */
export async function deleteUserCollection(
  token: string,
  collectionId: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<CustomListRead> {
  const res = await http.delete<CustomListRead>(`/api/v1/user_collections/${collectionId}`, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
  return mapReadFromBackend(res);
}

/**
 * 向片单添加影片：POST /api/v1/user_collections/{collection_id}/add_movies
 * Body: { movie_ids: string[] }
 */
export async function addMoviesToCollection(
  token: string,
  collectionId: string,
  movieIds: string[],
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<Record<string, unknown>> {
  const body = { movie_ids: movieIds };
  return http.post<Record<string, unknown>>(
    `/api/v1/user_collections/${collectionId}/add_movies`,
    body,
    {
      token,
      baseURL: options?.baseURL,
      signal: options?.signal,
    }
  );
}

/**
 * 从片单移除影片：POST /api/v1/user_collections/{collection_id}/remove_movies
 * Body: { movie_ids: string[] }
 */
export async function removeMoviesFromCollection(
  token: string,
  collectionId: string,
  movieIds: string[],
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<Record<string, unknown>> {
  const body = { movie_ids: movieIds };
  return http.post<Record<string, unknown>>(
    `/api/v1/user_collections/${collectionId}/remove_movies`,
    body,
    {
      token,
      baseURL: options?.baseURL,
      signal: options?.signal,
    }
  );
}

/**
 * 获取片单影片：GET /api/v1/user_collections/{collection_id}/movies
 * 返回 List[MovieRead]
 */
export async function getCollectionMovies(
  token: string,
  collectionId: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<MovieRead[]> {
  return http.get<MovieRead[]>(`/api/v1/user_collections/${collectionId}/movies`, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}