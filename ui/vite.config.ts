import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Ports come from .env (exported by the Makefile)
const apiPort = process.env.API_PORT ?? "8000";
const apiHost = process.env.API_HOST ?? "127.0.0.1";

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.UI_PORT ?? 5173),
    proxy: { "/api": `http://${apiHost}:${apiPort}` },
  },
});
