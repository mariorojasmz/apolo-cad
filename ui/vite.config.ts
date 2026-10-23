import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `/api/cosim/vivo` es un WebSocket (la sesión en vivo, V8.4): va ANTES de `/api`, que es sólo HTTP.
const proxy = {
  "/api/cosim/vivo": { target: "ws://127.0.0.1:8000", ws: true },
  "/api": "http://127.0.0.1:8000",
  "/ws": { target: "ws://127.0.0.1:8000", ws: true },
};

export default defineConfig({
  plugins: [react()],
  server: { proxy },
  preview: { proxy },
});
