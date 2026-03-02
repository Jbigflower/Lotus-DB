// 搜索 API 方法

import { http } from "./http";
import type { GlobalSearchResult, GlobalSearchParams, SemanticSearchParams, SemanticSearchResult } from "../types/search";

/**
 * 全局搜索
 * GET /api/v1/search/
 */
export async function globalSearch(
  token: string,
  params: GlobalSearchParams,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<GlobalSearchResult> {
  const qp = new URLSearchParams();
  
  // 必需参数
  qp.set("q", params.q);
  
  // 可选参数
  if (params.page != null) qp.set("page", String(params.page));
  if (params.size != null) qp.set("size", String(params.size));
  if (params.only_me != null) qp.set("only_me", String(params.only_me));
  if (params.type != null) qp.set("type", params.type);

  return http.get<GlobalSearchResult>("/api/v1/search/", {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
    query: qp,
  });
}

/**
 * 语义搜索
 * POST /api/v1/search/ns
 */
export async function semanticSearch(
  token: string,
  params: SemanticSearchParams,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<SemanticSearchResult> {
  return http.post<SemanticSearchResult>("/api/v1/search/ns", params, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}