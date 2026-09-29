import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const { buildPlugin } = createRequire(import.meta.url)('./electron/ui-build-contract.cjs');

export default defineConfig({
  plugins: [react(), buildPlugin(fileURLToPath(new URL('.', import.meta.url)))],
  base: "/",
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:3910",
        changeOrigin: false,
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
