export enum UserRole {
  ADMIN = 'admin',
  USER = 'user',
  GUEST = 'guest',
}

export interface UserSettings {
  theme: string;
  language: string;
  auto_play: boolean;
  subtitle_enabled: boolean;
  quality_preference: string;
}

export interface UserBase {
  username: string;
  email: string;
  role: UserRole;
  permissions: string[];
  is_active: boolean;
  is_verified: boolean;
  settings: UserSettings;
}

export interface UserCreate extends UserBase {
  hashed_password: string;
}

export interface UserUpdate {
  settings?: UserSettings | null;
}

export interface UserInDB extends UserBase {
  id: string;
  hashed_password: string;
  last_login_at?: string | null;
  is_deleted: boolean;
  deleted_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserRead extends Omit<UserInDB, 'hashed_password'> {
  hashed_password?: string | null;
}

export interface UserPageResult {
  items: UserRead[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

/**
 * 路由层 Schema（请求/响应），与后端保持同名字段
 */
export interface UserCreateRequestSchema extends Omit<UserCreate, 'hashed_password'> {
  password: string;
  hashed_password?: string | null;
}

export type UserUpdateRequestSchema = UserUpdate;

export type UserReadResponseSchema = UserRead;

export type UserPageResultResponseSchema = UserPageResult;

export interface TokenResponse<TUser = UserRead> {
  access_token: string;
  token_type: string;
  user: TUser;
  session_id?: string | null;
}

export interface StatusPatchResponseSchema {
  status: string;
  user: UserRead;
}

export interface UserPasswordReset {
  new_password: string;
}

export interface UserPasswordChange {
  old_password: string;
  new_password: string;
}

export interface UserIdentityUpdate {
  username?: string | null;
  email?: string | null;
}

// 与后端 routers/schemas/user.py 新增保持一致
export interface UserRolePermissionsUpdateRequestSchema {
  role: UserRole;
  permissions?: string[] | null;
}

// 映射后端 DeviceSessionRead（routers/schemas/auth.py）
export interface DeviceSessionRead {
  session_id: string;
  ip?: string | null;
  user_agent?: string | null;
  platform?: string | null;
  alias?: string | null;
  created_at: string;
  last_active_at?: string | null;
  is_current: boolean;
}
