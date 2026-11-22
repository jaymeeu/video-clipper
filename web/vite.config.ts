import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

// In development the app calls /api/*, and Vite forwards it to the clippers API,
// adding the X-API-Key header on the way, so the key never reaches the browser.
// (In production, Caddy does the same job: see web/Caddyfile.)
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "..", ""); // the repo root's .env, same as the Python side
  const apiKey = env.CLIPPERS_API_KEY;
  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: env.CLIPPERS_API_URL || "http://127.0.0.1:8000",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
          headers: apiKey ? { "X-API-Key": apiKey } : {},
        },
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      css: false,
    },
  };
});
