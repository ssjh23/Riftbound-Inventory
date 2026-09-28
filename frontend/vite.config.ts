/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dev server proxies API and image requests to the Python backend, so the
// browser only ever talks to one origin. This sidesteps CORS entirely in dev
// and means no backend URL is hardcoded into the frontend. `host: true` also
// serves the app on the LAN, so a phone on the same network can browse the
// collection at http://<pc-ip>:5173.
// In Docker Compose the frontend container proxies to the backend service name.
const apiTarget = process.env.VITE_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    proxy: {
      "/api": apiTarget,
      "/images": apiTarget,
    },
  },
  test: {
    environment: "node",
  },
});
