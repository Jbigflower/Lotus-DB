// 任务类型定义：与后端 models/tasks/task_models.py 与 routers/schemas/task.py 对齐

export enum TaskType {
  IMPORT = "import",
  EXPORT = "export",
  BACKUP = "backup",
  ANALYSIS = "analysis",
  MAINTENANCE = "maintenance",
  DOWNLOAD = "download",
  OTHER = "other",
}

export enum TaskSubType {
  // IMPORT
  MOVIE_IMPORT = "import_movies",

  // ANALYSIS
  EXTRACT_METADATA = "extract_metadata",
  THUMB_SPRITE_GENERATE = "generate_thumb_sprite",
  SYNC_EXTERNAL_SUBTITLES = "sync_external_subtitles",

  // MAINTENANCE
  REFACTOR_LIBRARY_STRUCTURE = "refactor_library_structure",
  CLEANUP_LIBRARY_FILES = "cleanup_library_files",

  // OTHER
  SYNC_DIRTY_COLLECTIONS = "sync_dirty_collections",
  REFRESH_COLLECTION_CACHE = "refresh_collection_cache",
  DOWNLOAD_MOVIE_FILE = "download_movie_file",
  DOWNLOAD_ACTOR_FILE = "download_actor_file",
  DOWNLOAD_SUBTITLE_FILE = "download_subtitle_file",
}

export enum TaskStatus {
  PENDING = "pending",
  RUNNING = "running",
  COMPLETED = "completed",
  FAILED = "failed",
  CANCELLED = "cancelled",
  PAUSED = "paused",
  RETRYING = "retrying",
}

// 数值枚举（与后端 int Enum 对齐）
export enum TaskPriority {
  LOW = 0,
  NORMAL = 20,
  HIGH = 50,
  URGENT = 100,
}

export interface ProgressInfo {
  current_step: string;
  total_steps: number;
  completed_steps: number;
}

export interface TaskBase {
  name: string;
  description: string;
  task_type: TaskType;
  sub_type: TaskSubType;
  priority: TaskPriority;
  parameters: Record<string, unknown>;
  status: TaskStatus;
  progress: ProgressInfo;
  result: Record<string, unknown>;
}

export interface TaskInDB extends TaskBase {
  id: string;

  user_id?: string | null;
  parent_task_id?: string | null;

  error_message?: string | null;
  error_details?: Record<string, unknown> | null;

  scheduled_at?: string | null;
  retry_count: number;
  max_retries: number;
  timeout_seconds: number;

  created_at: string;
  started_at?: string | null;
  retry_at?: string | null;
  completed_at?: string | null;
  updated_at: string;
}

export interface TaskCreate extends TaskBase {
  user_id?: string | null;
  parent_task_id?: string | null;
  max_retries: number;
  timeout_seconds: number;
  scheduled_at?: string | null;
}

export interface TaskUpdate {
  status?: TaskStatus | null;
  progress?: ProgressInfo | null;
  error_message?: string | null;
  result?: Record<string, unknown> | null;
}

export type TaskRead = TaskInDB;

export interface TaskPageResult {
  items: TaskRead[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

// 路由层 Schema 别名（与后端 routers/schemas/task.py 保持同名）
export type TaskCreateRequestSchema = TaskCreate;
export type TaskUpdateRequestSchema = TaskUpdate;
export type TaskReadResponseSchema = TaskRead;
export type TaskPageResultResponseSchema = TaskPageResult;