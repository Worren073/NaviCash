import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";
import path from "node:path";
import process from "node:process";

const apiTarget =
  process.env.VITE_API_PROXY_TARGET ??
  process.env.VITE_DEV_API_PROXY_TARGET ??
  "http://localhost:8000";

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg"],
      manifest: {
        name: "NaviCash — Finanzas personales",
        short_name: "NaviCash",
        description:
          "Lleva tus cobros, pagos, pendientes, retrasos y metas de ahorro desde el bolsillo.",
        theme_color: "#006a61",
        background_color: "#ffffff",
        display: "standalone",
        start_url: "/",
        lang: "es",
        icons: [
          {
            src: "/pwa-192.png",
            sizes: "192x192",
            type: "image/png",
          },
          {
            src: "/pwa-512.png",
            sizes: "512x512",
            type: "image/png",
          },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
      },
    }),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
});