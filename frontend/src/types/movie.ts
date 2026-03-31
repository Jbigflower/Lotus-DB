// 电影类型定义，映射后端 models/movies/movie_models.py 与 routers/schemas/movie.py

export interface MovieMetadata {
  duration?: number;
  country: string[];
  language?: string;
}

export interface MovieBase {
  library_id: string;
  title: string;
  title_cn: string;
  directors: string[];
  actors: string[];
  description: string;
  description_cn: string;
  // 后端为 Optional[date]，序列化为字符串或 null
  release_date?: string | null;
  genres: string[];
  // 后端有 default_factory，因此在实际对象中始终存在
  metadata: MovieMetadata;
  // 后端为 Optional[float]，取值范围 0~10
  rating?: number | null;
  tags: string[];
}

export type MovieCreate = MovieBase

export interface MovieUpdate {
  library_id: string;
  title?: string;
  title_cn?: string;
  directors?: string[];
  actors?: string[];
  description?: string;
  description_cn?: string;
  release_date?: string | null;
  genres?: string[];
  metadata?: MovieMetadata;
  rating?: number | null;
  tags?: string[];
}

export interface MovieInDB extends MovieBase {
  id: string;
  has_poster: boolean;
  has_backdrop: boolean;
  has_thumbnail: boolean;
  is_deleted: boolean;
  deleted_at?: string | null;
  created_at: string;
  updated_at: string;
  is_favoriter?: boolean;
  is_watchLater?: boolean;
}

export type MovieRead = MovieInDB

export interface MoviePageResult {
  items: MovieRead[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

// 路由层 Schema（routers/schemas/movie.py）
export type MovieCreateRequestSchema = MovieCreate;

export type MovieUpdateRequestSchema = MovieUpdate

export type MovieReadResponseSchema = MovieRead

export type MoviePageResultResponseSchema = MoviePageResult

export interface MovieCreateResponse {
  movie_info: MovieReadResponseSchema;
  task_id?: string | null;
}
