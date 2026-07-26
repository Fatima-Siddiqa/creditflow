import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // 0.0.0.0 -- required so ngrok (or any external tunnel) can reach the dev server
    allowedHosts: [".ngrok-free.app"], // wildcard for ngrok's rotating free-tier subdomains
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.js",
    globals: true,
  },
});