export enum LibraryType {
  MOVIE = 'movie',
  TV = 'tv',
}

export interface LibraryBase {
  name: string;
  root_path: string;
  type: LibraryType;
  description: string;
  scan_interval: number;
  auto_import: boolean;
  auto_import_scan_path?: string | null;
  auto_import_supported_formats?: string[] | null;
  activated_plugins?: Record<string, string[]>;
  is_public: boolean;
  is_active: boolean;
}

export interface LibraryCreate extends Omit<LibraryBase, 'root_path'> {
  user_id: string;
  root_path?: string | null;
}

export interface LibraryUpdate {
  name?: string | null;
  root_path?: string | null;
  description?: string | null;
  scan_interval?: number | null;
  auto_import?: boolean | null;
  auto_import_scan_path?: string | null;
  supported_formats?: string[] | null;
  activated_plugins?: Record<string, string[]> | null;
}

export interface LibraryInDB extends LibraryBase {
  id: string;
  user_id: string;
  is_deleted: boolean;
  deleted_at?: string | null;
  created_at: string;
  updated_at: string;
}

export type LibraryRead = LibraryInDB;

export interface LibraryPageResult {
  items: LibraryRead[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

/**
 * 路由层 Schema（请求/响应），与后端保持同名字段
 */
export interface LibraryCreateRequestSchema extends Omit<LibraryCreate, 'user_id'> {
  user_id?: string | null;
  root_path?: string | null;

  // 与后端 routers/schemas/library.py 路由层新增插件选择保持一致
  metadata_plugins?: string[] | null;
  subtitle_plugins?: string[] | null;
}

export type LibraryUpdateRequestSchema = LibraryUpdate;

export type LibraryReadResponseSchema = LibraryRead;

export type LibraryPageResultResponseSchema = LibraryPageResult;
