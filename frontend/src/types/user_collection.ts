export enum CustomListType {
  FAVORITE = "favorite",
  WATCHLIST = "watchlist",
  CUSTOMLIST = "customlist", // 注意后端模型为 customlist
}

export interface CustomListBase {
  name: string;
  type: CustomListType;
  description: string;
  movies: string[];
  is_public: boolean;
}

export interface CustomListCreate extends CustomListBase {
  user_id: string;
}

export interface CustomListUpdate {
  name?: string | null;
  description?: string | null;
  movies?: string[] | null;
}

export interface CustomListInDB extends CustomListBase {
  id: string;
  user_id: string;
  movies: string[];
  is_deleted: boolean;
  deleted_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export type CustomListRead = CustomListInDB;

export interface CustomListPageResult {
  items: CustomListRead[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

/**
 * 路由层 Schema（请求/响应），与后端保持同名字段
 */
export interface CustomListCreateRequestSchema extends Omit<CustomListCreate, "user_id"> {
  // 后端依赖注入 current_user，允许前端不传
  user_id?: string | null;
}

export type CustomListUpdateRequestSchema = CustomListUpdate;

export type CustomListReadResponseSchema = CustomListRead;

export type CustomListPageResultResponseSchema = CustomListPageResult;

/**
 * 片单影片批量增删接口的请求体（路由中 AddMoviesSchema）
 */
export interface CollectionMovieIdsPayload {
  movie_ids: string[];
}