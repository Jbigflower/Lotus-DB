import { http } from './http'
import type {
  UserProfileDetails,
  DisplaySettings,
  PlayerSettings,
} from '../types/user_settings'

export async function getUserProfile<T = UserProfileDetails>(
  token: string,
  options?: { baseURL?: string; signal?: AbortSignal }
) {
  return http.get<T>('/api/user/profile', { token, baseURL: options?.baseURL, signal: options?.signal })
}

export async function getDisplaySettings<T = DisplaySettings>(
  token: string,
  options?: { baseURL?: string; signal?: AbortSignal }
) {
  return http.get<T>('/api/user/settings/display', { token, baseURL: options?.baseURL, signal: options?.signal })
}

export async function getPlayerSettings<T = PlayerSettings>(
  token: string,
  options?: { baseURL?: string; signal?: AbortSignal }
) {
  return http.get<T>('/api/user/settings/player', { token, baseURL: options?.baseURL, signal: options?.signal })
}