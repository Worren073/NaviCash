import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { registerSW } from "virtual:pwa-register";
import { Toaster } from "sileo";

import "@/index.css";
import { AppProviders } from "@/app/providers";
import { router } from "@/app/router";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import { RouterProvider } from "react-router-dom";

// Registra el service worker de la PWA (vite-plugin-pwa, registerType: autoUpdate).
// Habilita instalabilidad, soporte offline del shell y actualización automática.
registerSW({ immediate: true });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppProviders>
      <ErrorBoundary>
        <RouterProvider router={router} />
      </ErrorBoundary>
      <Toaster position="top-center" theme="light" offset={{ top: 72 }} />
    </AppProviders>
  </StrictMode>
);