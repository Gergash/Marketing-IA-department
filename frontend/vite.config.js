import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true
      },
      "/static": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true
      },
      // Legales públicos (TikTok App Review) — mismo HTML que sirve el gateway/ngrok
      "/terminos": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/privacidad": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/terminos.pdf": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/privacidad.pdf": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/terms": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/privacy": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/terms-of-service": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/privacy-policy": { target: "http://127.0.0.1:8000", changeOrigin: true },
    }
  }
});
