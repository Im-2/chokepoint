import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// In dev, the API is the deployed backend so no local FalkorDB is needed.
const BACKEND = process.env.CHOKEPOINT_BACKEND ?? "https://trychokepoint.vercel.app";

export default defineConfig({
  plugins: [react()],
  // The build goes to the repo's public/ folder, which is committed: Vercel serves public/ from its CDN at
  // the site root, next to the FastAPI function that serves /api, /mcp, /docs and /healthz. (Files that a
  // build command generates there are NOT picked up, so the build is done locally and committed.)
  build: { outDir: "../public", emptyOutDir: true, sourcemap: false, target: "es2022" },
  server: {
    proxy: {
      "/api": { target: BACKEND, changeOrigin: true },
      "/healthz": { target: BACKEND, changeOrigin: true },
    },
  },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
