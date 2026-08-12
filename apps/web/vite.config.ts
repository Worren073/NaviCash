import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";
import path from "node:path";
import process from "node:process";

// https://vite.dev/config/
export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  if (command === "build" && !env.VITE_CAPTCHA_SITE_KEY) {
    throw new Error("VITE_CAPTCHA_SITE_KEY es obligatoria para build de producción");
  }

  const apiTarget =
    env.VITE_API_PROXY_TARGET ??
    process.env.VITE_API_PROXY_TARGET ??
    process.env.VITE_DEV_API_PROXY_TARGET ??
    "http://localhost:8000";

  return {
    plugins: [
      react(),
      tailwindcss(),
      VitePWA({
        registerType: "autoUpdate",
        includeAssets: ["favicon.svg", "favicon-192.svg", "favicon-512.svg"],
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
              src: "/favicon-192.svg",
              sizes: "192x192",
              type: "image/svg+xml",
              purpose: "any",
            },
            {
              src: "/favicon-512.svg",
              sizes: "512x512",
              type: "image/svg+xml",
              purpose: "any",
            },
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
    build: {
      rollupOptions: {
        output: {
          // M10 — code splitting: librerías estables en chunks propios.
          manualChunks(id: string) {
            if (!id.includes("node_modules")) return undefined;
            if (id.includes("@tanstack")) return "react-query";
            if (id.includes("react-router")) return "react-router";
            if (id.includes("i18next") || id.includes("react-i18next")) return "i18n";
            if (id.includes("motion") || id.includes("@motionone")) return "motion";
            if (id.includes("lucide")) return "lucide";
            if (id.includes("radix")) return "radix";
            if (
              id.includes("react-dom") ||
              id.includes("react/") ||
              id.includes("scheduler") ||
              id.includes("jsx-runtime")
            ) {
              return "react-vendor";
            }
            return "vendor";
          },
        },
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
  };
});
