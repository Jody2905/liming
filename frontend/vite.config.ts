/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The build goes straight into the Python package, so `py -m liming serve` can serve it
// without Node.js. In development, `npm run dev` proxies /api to the Python server.
export default defineConfig({
  plugins: [react()],
  base: "/static/",
  build: {
    outDir: "../liming/web",
    emptyOutDir: true,
    assetsInlineLimit: 0, // fonts and images stay files, so the strict Content Security Policy allows them
  },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  test: { environment: "node" },
});
