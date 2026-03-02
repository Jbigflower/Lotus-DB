import { http } from "./http";
import type { UserRead, UserCreateRequestSchema, TokenResponse, DeviceSessionRead } from "../types/user";

export type RegisterPayload = Pick<
  UserCreateRequestSchema,
  "username" | "email" | "password"
>;

export interface LoginPayload {
  username: string;
  password: string;
}

/**
 * 用户注册：POST /auth/register
 * 成功后后端会自动登录，并返回 TokenResponse
 */
export async function register<TUser = UserRead>(
  payload: RegisterPayload,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<TokenResponse<TUser>> {
  return http.post<TokenResponse<TUser>>("/auth/register", payload, {
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 用户登录：POST /auth/login
 * 使用 application/x-www-form-urlencoded 以兼容 OAuth2PasswordRequestForm
 */
export async function login<TUser = UserRead>(
  payload: LoginPayload,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<TokenResponse<TUser>> {
  const form = new URLSearchParams();
  form.set("username", payload.username);
  form.set("password", payload.password);

  return http.post<TokenResponse<TUser>>("/auth/login", form, {
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 用户注销：POST /auth/logout
 * 需要在 Authorization 中携带 Bearer Token
 */
export async function logout(
  token: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<{ status: string }> {
  return http.post<{ status: string }>("/auth/logout", undefined, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

// 设备会话列表：GET /auth/devices
export async function listDevices(
  token: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<DeviceSessionRead[]> {
  return http.get<DeviceSessionRead[]>("/auth/devices", {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

// 撤销指定设备：POST /auth/devices/revoke/{session_id}
export async function revokeDevice(
  token: string,
  sessionId: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<{ status: string }> {
  return http.post<{ status: string }>(`/auth/devices/revoke/${sessionId}`, undefined, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

// 撤销除当前外的所有设备：POST /auth/devices/revoke_all
export async function revokeAllDevices(
  token: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<{ status: string }> {
  return http.post<{ status: string }>(`/auth/devices/revoke_all`, undefined, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

// 重命名指定设备：PATCH /auth/devices/{session_id}，Body: { alias }
export async function renameDevice(
  token: string,
  sessionId: string,
  alias: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<{ status: string }> {
  return http.patch<{ status: string }>(`/auth/devices/${sessionId}`, { alias }, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

// ----------------------
// 可用性检查：用户名 / 邮箱
// ----------------------

export async function checkUsernameAvailability(
  username: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<{ available: boolean }> {
  const qp = new URLSearchParams();
  qp.set("username", username);
  return http.get<{ available: boolean }>("/auth/availability/username", {
    baseURL: options?.baseURL,
    signal: options?.signal,
    query: qp,
  });
}

export async function checkEmailAvailability(
  email: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<{ available: boolean }> {
  const qp = new URLSearchParams();
  qp.set("email", email);
  return http.get<{ available: boolean }>("/auth/availability/email", {
    baseURL: options?.baseURL,
    signal: options?.signal,
    query: qp,
  });
}

// ----------------------
// 邮箱验证码：发送 / 验证
// ----------------------

export async function sendEmailVerification(
  email: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<{ status: string }> {
  return http.post<{ status: string }>("/auth/email/verify/send", { email }, {
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

export async function confirmEmailVerification(
  email: string,
  code: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<{ status: string }> {
  return http.post<{ status: string }>("/auth/email/verify/confirm", { email, code }, {
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}
