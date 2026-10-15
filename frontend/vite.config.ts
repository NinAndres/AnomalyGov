/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// In development, /api is proxied to the backend (backend/AnomalyGov.Api, port 5183 by default).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: { "/api": env.VITE_DEV_API_TARGET || "http://localhost:5183" },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["src/test/setup.ts"],
    },
  };
});
