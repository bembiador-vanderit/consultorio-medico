import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "API_");
  const proxy = { "/api/v1": { target: env.API_PROXY_TARGET || "http://localhost:8000", changeOrigin: true } };
  return {
    plugins: [react(), tailwindcss()],
    server: { host: "0.0.0.0", proxy },
    preview: { proxy },
  };
});
