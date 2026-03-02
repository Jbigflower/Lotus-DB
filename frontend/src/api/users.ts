import { http } from "./http";
import type {
  UserRead,
  UserPageResult,
  UserCreateRequestSchema,
  UserUpdateRequestSchema,
  UserRole,
  UserPasswordReset,
  UserPasswordChange,
  UserIdentityUpdate,
} from "../types/user";

export interface ListUsersParams {
  page?: number;
  size?: number;
  query?: string;
  role?: UserRole;
  is_active?: boolean;
  is_verified?: boolean;
}

export async function ping(
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<{ status: string; router: string }> {
  return http.get<{ status: string; router: string }>("/api/v1/users/ping", {
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

export async function listUsers(
  token: string,
  params: ListUsersParams = {},
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<UserPageResult> {
  const qp = new URLSearchParams();
  if (params.page !== undefined) qp.set("page", String(params.page));
  if (params.size !== undefined) qp.set("size", String(params.size));
  if (params.query !== undefined && params.query !== null && params.query !== "") {
    qp.set("query", params.query);
  }
  if (params.role !== undefined && params.role !== null) {
    qp.set("role", params.role as unknown as string);
  }
  if (params.is_active !== undefined) qp.set("is_active", String(params.is_active));
  if (params.is_verified !== undefined) qp.set("is_verified", String(params.is_verified));

  return http.get<UserPageResult>("/api/v1/users/", {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
    query: qp,
  });
}

// 新增：批量获取用户ID映射 GET /api/v1/users/mapping?ids=id1,id2,...
export async function getUserMapping(
  token: string,
  ids: string[],
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<Record<string, string>> {
  const qp = new URLSearchParams();
  qp.set("ids", ids.join(","));
  return http.get<Record<string, string>>("/api/v1/users/mapping", {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
    query: qp,
  });
}

export async function getUser(
  token: string,
  userId: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<UserRead> {
  return http.get<UserRead>(`/api/v1/users/${userId}`, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

export async function createUser(
  token: string,
  payload: UserCreateRequestSchema,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<UserRead> {
  return http.post<UserRead>("/api/v1/users/", payload, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

export async function updateUser(
  token: string,
  userId: string,
  payload: UserUpdateRequestSchema,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<UserRead> {
  return http.patch<UserRead>(`/api/v1/users/${userId}`, payload, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

export async function setUserActive(
  token: string,
  userId: string,
  isActive: boolean,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<UserRead> {
  return http.patch<UserRead>(`/api/v1/users/${userId}/activate`, isActive, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

export async function setRolePermissions(
  token: string,
  userId: string,
  role: UserRole,
  permissions?: string[] | null,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<UserRead> {
  const body: { role: UserRole; permissions?: string[] | null } = { role };
  if (permissions !== undefined) body.permissions = permissions;
  return http.patch<UserRead>(`/api/v1/users/${userId}/role`, body, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

export async function resetPassword(
  token: string,
  userId: string,
  payload: UserPasswordReset,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<UserRead> {
  return http.patch<UserRead>(`/api/v1/users/${userId}/password/reset`, payload, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

export async function changePassword(
  token: string,
  userId: string,
  payload: UserPasswordChange,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<UserRead> {
  return http.patch<UserRead>(`/api/v1/users/${userId}/password/change`, payload, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

export async function updateIdentity(
  token: string,
  userId: string,
  payload: UserIdentityUpdate,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<UserRead> {
  return http.patch<UserRead>(`/api/v1/users/${userId}/identity`, payload, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

// 新增：批量获取用户头像签名 POST /api/v1/users/profiles/sign
export async function getUserProfilesSigned(
  token: string,
  ids: string[],
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<string[]> {
  return http.post<string[]>("/api/v1/users/profiles/sign", ids, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

// 新增：上传用户头像（multipart）POST /api/v1/users/{user_id}/profile
export async function uploadUserProfile(
  token: string,
  userId: string,
  file: File,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<{ message: string; ok: boolean }> {
  const formData = new FormData();
  formData.append("file", file);
  return http.post<{ message: string; ok: boolean }>(`/api/v1/users/${userId}/profile`, formData, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

// 修正：删除用户 DELETE /api/v1/users/{user_id}，返回字典 { message, success }
export async function deleteUser(
  token: string,
  userId: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<{ message: string; success: number }> {
  return http.delete<{ message: string; success: number }>(`/api/v1/users/${userId}`, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}