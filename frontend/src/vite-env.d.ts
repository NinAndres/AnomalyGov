/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend URL in production builds; empty means same origin (dev server proxies /api). */
  readonly VITE_API_URL?: string;
}
