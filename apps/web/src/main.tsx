import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@/index.css";
import { AppProviders } from "@/app/providers";
import { router } from "@/app/router";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import { RouterProvider } from "react-router-dom";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppProviders>
      <ErrorBoundary>
        <RouterProvider router={router} />
      </ErrorBoundary>
    </AppProviders>
  </StrictMode>
);