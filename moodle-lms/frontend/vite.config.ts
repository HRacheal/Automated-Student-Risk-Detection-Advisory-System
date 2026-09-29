import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the browser talks only to Vite; /api is proxied to the LMS backend, so the
// session cookie stays same-origin and no Moodle token ever reaches the browser.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8100", changeOrigin: false } },
  },
  preview: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8100", changeOrigin: false } },
  },
});
