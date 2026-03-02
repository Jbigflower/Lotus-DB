/// <reference types="vite/client" />
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface Window {
  LOTUS_CONFIG?: {
    API_BASE_URL?: string;
    MEDIA_BASE_URL?: string;
  }
}

// 为 .vue 文件提供类型声明，修复“找不到模块或其类型声明”的诊断
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}
