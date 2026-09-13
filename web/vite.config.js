import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API is served by the same deployment (api/index.py), so in development
// everything under /api is proxied to a local run of it rather than mocked.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
  build: { outDir: "dist", sourcemap: true },
});
