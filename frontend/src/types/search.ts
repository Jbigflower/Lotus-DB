// 搜索类型定义，映射后端全局搜索返回结果

import type { MoviePageResult } from "./movie";
import type { AssetPageResult } from "./asset";
import type { UserAssetPageResult } from "./user_asset";
import type { CustomListPageResultResponseSchema } from "./user_collection";
import type { LibraryPageResult } from "./library";

/**
 * 全局搜索结果接口
 * 对应后端 SearchService.search 方法的返回结果
 */
export interface GlobalSearchResult {
  movies: MoviePageResult;
  movie_assets: AssetPageResult;
  user_assets: UserAssetPageResult;
  collections: CustomListPageResultResponseSchema;
  libraries: LibraryPageResult;
}

/**
 * 全局搜索请求参数
 */
export interface GlobalSearchParams {
  /** 搜索关键词 */
  q: string;
  /** 页码，默认为 1 */
  page?: number;
  /** 每页数量，默认为 20，最大 200 */
  size?: number;
  /** 是否只返回我的资源，默认为 false */
  only_me?: boolean;
  /** 搜索类型：summary, movies, libraries, user_assets, collections, movie_assets */
  type?: string;
}

/**
 * 语义搜索请求参数
 */
export interface SemanticSearchParams {
  /** 搜索关键词 */
  query: string;
  /** 页码 */
  page?: number;
  /** 每页数量 */
  size?: number;
  /** 是否只返回我的资源 */
  only_me?: boolean;
  /** 搜索类型: movies, notes, subtitles */
  types?: string[];
  /** 向量召回数量 */
  top_k?: number;
  /** 向量分权重 (0-1) */
  vector_weight?: number;
  /** 关键词分权重 (0-1) */
  keyword_weight?: number;
  /** 同一资产最大片段数 */
  max_per_parent?: number;
  /** 是否启用缓存 */
  use_cache?: boolean;
}

export interface Chunk {
  id: string;
  parent_id: string;
  content: string;
  [key: string]: unknown;
}

export interface SearchResultItem<T> {
  chunk: Chunk;
  data: T;
  movie?: Record<string, unknown>;
  score: number;
  vector_score: number;
  keyword_score: number;
}

/**
 * 语义搜索响应接口
 */
export interface SemanticSearchResult {
  status: string;
  query: {
    raw: string;
    normalized: string;
    collapsed: string;
    tokens: string[];
    variants: string[];
  };
  data: {
    movies?: {
      items: Array<{
        chunk: Chunk;
        movie: MoviePageResult["items"][0] | null;
        score: number;
        vector_score: number;
        keyword_score: number;
      }>;
      total: number;
      page: number;
      size: number;
      pages: number;
    };
    notes?: {
      items: Array<{
        chunk: Chunk;
        note: Record<string, unknown>;
        movie: Record<string, unknown>;
        score: number;
        vector_score: number;
        keyword_score: number;
      }>;
      total: number;
      page: number;
      size: number;
      pages: number;
    };
    subtitles?: {
      items: Array<{
        chunk: Chunk;
        subtitle: Record<string, unknown>;
        movie: Record<string, unknown>;
        score: number;
        vector_score: number;
        keyword_score: number;
      }>;
      total: number;
      page: number;
      size: number;
      pages: number;
    };
  };
  meta: {
    page: number;
    size: number;
    cache: boolean;
    timing_ms: {
      rewrite: number;
      embedding: number;
      search: number;
      rank: number;
      assemble: number;
      total: number;
    };
  };
}