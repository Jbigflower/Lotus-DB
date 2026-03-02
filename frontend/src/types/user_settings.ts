export interface UserProfileDetails {
  id?: string | null;
  username: string;
  email: string;
  role: string;
  avatar_url?: string | null;
  backup_email?: string | null;
  identity?: string | null;
  account_id?: string | null;
}

export interface DisplaySettings {
  language: string;
  timezone?: string | null;
  theme: 'light' | 'dark' | 'system' | string;
  custom_css?: string | null;
  section_size?: 'compact' | 'comfortable' | string;
}

export interface PlayerSettings {
  // 字幕
  auto_load_subtitle?: boolean;
  prefer_local_subtitle?: boolean;
  online_subtitle_search?: boolean;

  // 音轨
  audio_prefer_language?: string | null;
  audio_prefer_source?: string | null;

  // 播放
  speed_step?: number | null; // 倍速快捷步
  auto_play?: boolean;

  // 默认模式
  subtitle_default_mode?: 'auto' | 'origin' | 'off' | string;
  audio_default_mode?: 'auto' | 'native' | 'fallback' | string;

  // 最小界面
  minimal_ui_max_level?: number | null;
}