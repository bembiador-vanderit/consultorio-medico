import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode, command, isPreview }) => {
  const env = loadEnv(mode, ".", "API_");
  const proxy = { "/api/v1": { target: env.API_PROXY_TARGET || "http://localhost:8000", changeOrigin: false } };
  // Explicit development/staging hosts only; no wildcard or production preview override.
  const hostEnv = loadEnv(mode, ".", "VITE_ALLOWED_HOSTS");
  const extraHosts = (hostEnv.VITE_ALLOWED_HOSTS || "").split(",").map((host) => host.trim()).filter(Boolean);
  if (extraHosts.some((host) => !/^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/i.test(host) || host.includes(".."))) {
    throw new Error("VITE_ALLOWED_HOSTS must contain exact hostnames only");
  }
  const allowedHosts = command === "serve" && !isPreview && ["development", "staging"].includes(mode)
    ? ["atlas", ...extraHosts]
    : [];
  return {
    plugins: [react(), tailwindcss()],
    // Docker Desktop does not reliably emit host bind-mount changes to Chokidar.
    // Polling keeps Vite's transformed module cache aligned with the Windows checkout.
    server: { host: "0.0.0.0", allowedHosts, proxy, watch: { usePolling: true, interval: 300 } },
    preview: { proxy },
  };
});
