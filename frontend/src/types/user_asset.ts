export enum UserAssetType {
  NOTE = "note",
  SCREENSHOT = "screenshot",
  CLIP = "clip",
  REVIEW = "review",
}

export enum AssetStoreType {
  LOCAL = "local",
  S3 = "s3",
}

export interface ClipMetadata {
  type: UserAssetType.CLIP;
  size?: number;
  duration?: number;
  quality?: string;
  codec?: string;
  has_thumbnail?: boolean;
  has_sprite?: boolean;
}

export interface ScreenShotMetadata {
  type: UserAssetType.SCREENSHOT;
  size?: number;
  width?: number;
  height?: number;
}

export type UserAssetMetadata = ClipMetadata | ScreenShotMetadata;

export interface UserAssetBase {
  movie_id: string;
  type: UserAssetType;
  name: string;
  related_movie_ids: string[];
  tags: string[];
  is_public: boolean;
  permissions: string[];
  path: string;
  store_type: AssetStoreType;
  actual_path?: string | null;
  content?: string | null;
  metadata?: UserAssetMetadata | null;
}

export interface UserAssetCreate extends UserAssetBase {
  user_id: string;
}

export interface UserAssetUpdate {
  // 后端为必填：name
  name: string;
  related_movie_ids?: string[] | null;
  tags?: string[] | null;
  content?: string | null;
  metadata?: UserAssetMetadata | null;
}

export interface UserAssetInDB {
  id: string;
  user_id: string;
  is_deleted: boolean;
  deleted_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  movie_info?: Record<string, unknown> | null;
  require_allocate: boolean;
}

export type UserAssetRead = UserAssetBase & UserAssetInDB;

export interface UserAssetPageResult {
  items: UserAssetRead[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export interface PartialPageResult<T = unknown> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

/**
 * 路由层 Schema（请求/响应），与后端保持同名字段
 */
export interface UserAssetCreateRequestSchema extends Omit<UserAssetCreate, "user_id" | "name" | "path" | "actual_path"> {
  user_id?: string | null;
  name?: string | null;
  path?: string | null;
  actual_path?: string | null;
}

export type UserAssetUpdateRequestSchema = UserAssetUpdate;

export type UserAssetReadResponseSchema = UserAssetRead;

export type UserAssetPageResultResponseSchema = UserAssetPageResult;

export type UserAssetListResponseUnion<T = unknown> = PartialPageResult<T> | UserAssetPageResult;

// 与后端 routers/schemas/user_asset.py 对齐：复杂列表查询
export interface UserAssetListQuerySchema {
  query?: string | null;
  user_id?: string | null;
  movie_id?: string | null;
  asset_type?: UserAssetType[] | null;
  tags?: string[] | null;
  is_public?: boolean | null;
  page: number;
  size: number;
  sort?: Array<[string, number]> | null; // 例如 [['created_at', -1]]
  projection?: Record<string, number> | null; // 返回 PartialPageResult
}

export interface UserAssetIdsRequestSchema {
  asset_ids: string[];
}

export interface UserAssetBatchUpdateRequestSchema {
  asset_ids: string[];
  patch: UserAssetUpdateRequestSchema;
}

export interface UserAssetSetActiveStatusRequestSchema {
  asset_ids: string[];
  is_public: boolean;
}

export interface UserAssetAllocateRequestSchema {
  allocate_map: Record<string, string[]>;
}