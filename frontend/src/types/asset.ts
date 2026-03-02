// 资产类型定义，映射后端 models/movies/asset_models.py 与 routers/schemas/asset.py

export enum AssetType {
  VIDEO = 'video',
  SUBTITLE = 'subtitle',
  IMAGE = 'image',
}

export enum AssetStoreType {
  LOCAL = 'local',
  S3 = 's3',
}

export interface VideoMetadata {
  type: AssetType.VIDEO;
  size: number;
  duration?: number;
  quality?: string;
  codec?: string;
  has_thumbnail?: boolean;
  has_sprite?: boolean;
  width?: number;
  height?: number;
}

export interface SubtitleMetadata {
  type: AssetType.SUBTITLE;
  size: number;
  language?: string;
}

export interface ImageMetadata {
  type: AssetType.IMAGE;
  size: number;
  width?: number;
  height?: number;
}

export type AssetMetadata = VideoMetadata | SubtitleMetadata | ImageMetadata;

export interface AssetBase {
  library_id: string;
  movie_id: string;
  type: AssetType;
  name: string; // 播放时显示
  path: string;
  store_type: AssetStoreType;
  actual_path?: string;
  description: string;
  tags?: string[];
}

export type AssetCreate = AssetBase

export interface AssetUpdate {
  name?: string;
  description?: string;
  actual_path?: string;
  tags?: string[];
  metadata?: AssetMetadata;
}

export interface AssetInDB extends AssetBase {
  id: string;
  metadata?: AssetMetadata;
  is_deleted: boolean;
  deleted_at?: string | null;
  created_at: string;
  updated_at: string;
}

export type AssetRead = AssetInDB

export interface AssetPageResult {
  items: AssetRead[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

// 路由层 Schema（routers/schemas/asset.py）
export type AssetCreateRequestSchema = Omit<AssetCreate, "path" | "library_id">;

export type AssetUpdateRequestSchema = AssetUpdate

export type AssetReadResponseSchema = AssetRead

export type AssetPageResultResponseSchema = AssetPageResult

// 与后端 routers/schemas/asset.py 新增保持一致
export interface AssetBatchUpdateRequestSchema {
  asset_ids: string[];
  patch: AssetUpdateRequestSchema;
}
