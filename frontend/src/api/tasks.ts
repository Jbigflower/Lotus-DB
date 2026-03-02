import { http } from "./http";
import type {
  TaskType,
  TaskSubType,
  TaskStatus,
  TaskPriority,
  TaskRead,
  TaskPageResult,
  ProgressInfo,
} from "@/types/task";

/**
 * 列表：GET /api/v1/tasks/
 */
export interface ListTasksParams {
  page?: number;
  size?: number;
  query?: string;
  task_type?: TaskType;
  sub_type?: TaskSubType;
  status?: TaskStatus;
  priority?: TaskPriority;
  user_id?: string;
}

export async function listTasks(
  token: string,
  params: ListTasksParams = {},
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<TaskPageResult> {
  const qp = new URLSearchParams();
  if (params.page !== undefined) qp.set("page", String(params.page));
  if (params.size !== undefined) qp.set("size", String(params.size));
  if (params.query) qp.set("query", params.query);
  if (params.task_type !== undefined && params.task_type !== null) {
    qp.set("task_type", params.task_type as unknown as string);
  }
  if (params.sub_type !== undefined && params.sub_type !== null) {
    qp.set("sub_type", params.sub_type as unknown as string);
  }
  if (params.status !== undefined && params.status !== null) {
    qp.set("status", params.status as unknown as string);
  }
  if (params.priority !== undefined && params.priority !== null) {
    qp.set("priority", String(params.priority));
  }
  if (params.user_id) qp.set("user_id", params.user_id);

  return http.get<TaskPageResult>("/api/v1/tasks/", {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
    query: qp,
  });
}

/**
 * 详情：GET /api/v1/tasks/{task_id}
 */
export async function getTaskDetail(
  token: string,
  taskId: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<TaskRead> {
  return http.get<TaskRead>(`/api/v1/tasks/${taskId}`, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 取消任务：PATCH /api/v1/tasks/{task_id}/cancel
 */
export async function cancelTask(
  token: string,
  taskId: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<TaskRead> {
  return http.patch<TaskRead>(`/api/v1/tasks/${taskId}/cancel`, undefined, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 获取进度：GET /api/v1/tasks/{task_id}/progress
 */
export async function getTaskProgress(
  token: string,
  taskId: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<ProgressInfo> {
  return http.get<ProgressInfo>(`/api/v1/tasks/${taskId}/progress`, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}

/**
 * 重试任务：POST /api/v1/tasks/{task_id}/retry
 */
interface RetryTaskResponse {
  data: TaskRead;
  task: { task_id: string; task_name: string };
}

export async function retryTask(
  token: string,
  taskId: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<TaskRead> {
  const res = await http.post<RetryTaskResponse>(`/api/v1/tasks/${taskId}/retry`, undefined, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
  return res.data;
}

/**
 * 删除任务：DELETE /api/v1/tasks/{task_id}
 */
export async function deleteTask(
  token: string,
  taskId: string,
  options?: { baseURL?: string; signal?: AbortSignal }
): Promise<boolean> {
  return http.delete<boolean>(`/api/v1/tasks/${taskId}`, {
    token,
    baseURL: options?.baseURL,
    signal: options?.signal,
  });
}