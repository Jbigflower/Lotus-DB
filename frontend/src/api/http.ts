// http 核心封装：统一 baseURL、headers、body、错误处理

export const DEFAULT_BASE_URL =
  window.LOTUS_CONFIG?.API_BASE_URL ??
  import.meta.env?.VITE_API_BASE_URL ??
  "http://localhost:8000";

export const DEFAULT_MEDIA_URL =
  window.LOTUS_CONFIG?.MEDIA_BASE_URL ?? DEFAULT_BASE_URL;

export function resolveBaseURL(baseURL?: string): string {
  return (baseURL ?? DEFAULT_BASE_URL).replace(/\/$/, "");
}

export function resolveMediaURL(baseURL?: string): string {
  return (baseURL ?? DEFAULT_MEDIA_URL).replace(/\/$/, "");
}

let authErrorHandler: ((status: number, data: unknown) => void) | null = null;
export function setAuthErrorHandler(
  fn: ((status: number, data: unknown) => void) | null
): void {
  authErrorHandler = fn;
}

export async function handleResponse<T>(res: Response): Promise<T> {
  const text = await res.text();
  let data: unknown = null;

  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }

  if (!res.ok) {
    let message = res.statusText;
    if (typeof data === "object" && data !== null) {
      const obj = data as Record<string, unknown>;
      const detail = obj["detail"];
      const msg = obj["message"];
      if (typeof detail === "string") message = detail;
      else if (typeof msg === "string") message = msg;
    } else if (typeof data === "string") {
      message = data;
    }
    if (res.status === 401 && authErrorHandler) {
      try { authErrorHandler(res.status, data); } catch {}
    }
    const error = new Error(message);
    Object.assign(error, { status: res.status, data });
    throw error;
  }
  return data as T;
}

export interface HttpRequestOptions {
  baseURL?: string;
  token?: string;
  headers?: HeadersInit;
  signal?: AbortSignal;
  query?: URLSearchParams | Record<string, unknown> | null | undefined;
}

function normalizePath(path: string): string {
  return path.startsWith("/") ? path : `/${path}`;
}

function buildQuery(init: HttpRequestOptions["query"]): string | null {
  if (!init) return null;
  if (init instanceof URLSearchParams) {
    const qs = init.toString();
    return qs ? `?${qs}` : null;
  }
  const qp = new URLSearchParams();
  const obj = init as Record<string, unknown>;
  for (const [key, val] of Object.entries(obj)) {
    if (val === undefined || val === null) continue;
    if (Array.isArray(val)) {
      for (const v of val) qp.append(key, String(v));
    } else {
      qp.set(key, String(val));
    }
  }
  const qs = qp.toString();
  return qs ? `?${qs}` : null;
}

function mergeHeaders(token: string | undefined, headers?: HeadersInit): HeadersInit {
  const base: HeadersInit = {};
  if (token) base["Authorization"] = `Bearer ${token}`;
  return { ...base, ...(headers ?? {}) };
}

function makeBodyAndHeaders(
  body?: unknown,
  headers?: HeadersInit
): { cookedBody?: BodyInit; headers: HeadersInit } {
  const hdrs: Record<string, string> = { ...(headers as Record<string, string> ?? {}) };

  if (body === undefined || body === null) {
    return { cookedBody: undefined, headers: hdrs };
  }

  if (body instanceof URLSearchParams) {
    if (!hdrs["Content-Type"]) {
      hdrs["Content-Type"] = "application/x-www-form-urlencoded";
    }
    return { cookedBody: body.toString(), headers: hdrs };
  }

  if (typeof FormData !== "undefined" && body instanceof FormData) {
    return { cookedBody: body, headers: hdrs };
  }

  if (typeof Blob !== "undefined" && body instanceof Blob) {
    return { cookedBody: body, headers: hdrs };
  }

  if (typeof body === "string") {
    return { cookedBody: body, headers: hdrs };
  }

  if (!hdrs["Content-Type"]) {
    hdrs["Content-Type"] = "application/json";
  }
  return { cookedBody: JSON.stringify(body), headers: hdrs };
}

async function doFetch<T>(
  method: string,
  path: string,
  body: unknown,
  opts: HttpRequestOptions
): Promise<T> {
  const base = resolveBaseURL(opts.baseURL);
  const qs = buildQuery(opts.query);
  const url = `${base}${normalizePath(path)}${qs ?? ""}`;

  const { cookedBody, headers } = makeBodyAndHeaders(body, mergeHeaders(opts.token, opts.headers));

  const res = await fetch(url, {
    method,
    headers,
    body: cookedBody,
    signal: opts.signal,
  });

  return handleResponse<T>(res);
}

export const http = {
  get:  <T>(path: string, opts: HttpRequestOptions = {}) => doFetch<T>("GET",    path, undefined, opts),
  post: <T>(path: string, body?: unknown, opts: HttpRequestOptions = {}) => doFetch<T>("POST",   path, body,     opts),
  patch:<T>(path: string, body?: unknown, opts: HttpRequestOptions = {}) => doFetch<T>("PATCH",  path, body,     opts),
  delete:<T>(path: string, opts: HttpRequestOptions = {}) => doFetch<T>("DELETE", path, undefined, opts),
  // 新增：支持 DELETE 携带请求体（用于批量删除）
  deleteWithBody:<T>(path: string, body?: unknown, opts: HttpRequestOptions = {}) => doFetch<T>("DELETE", path, body, opts),
};
