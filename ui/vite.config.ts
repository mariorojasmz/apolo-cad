import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// La API a la que apunta el proxy: 127.0.0.1:8000 por defecto; `APOLO_API=127.0.0.1:8106` para
// probar la UI contra otra API (p. ej. la de prueba de `.claude/launch.json`).
const api = process.env.APOLO_API || "127.0.0.1:8000";

// `/api/cosim/vivo` es un WebSocket (la sesión en vivo, V8.4): va ANTES de `/api`, que es sólo HTTP.
const proxy = {
  "/api/cosim/vivo": { target: `ws://${api}`, ws: true },
  "/api": `http://${api}`,
  "/ws": { target: `ws://${api}`, ws: true },
};

export default defineConfig({
  plugins: [react()],
  server: { proxy },
  preview: { proxy },
});
