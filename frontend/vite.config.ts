import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const designDir = path.resolve(import.meta.dirname, "../design");

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "src"),
      "@design": designDir,
    },
  },
  server: {
    // design/ está fuera de frontend/: hay que permitir que Vite lo sirva.
    fs: { allow: [import.meta.dirname, designDir] },
    // Mismo origen para la API: la cookie de sesión httpOnly viaja sin CORS.
    proxy: {
      "/api": process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000",
    },
    // En Docker sobre WSL2/macOS los eventos del sistema de archivos no siempre llegan.
    watch: { usePolling: true, interval: 300 },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
