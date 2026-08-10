import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { useState } from "react";
import type { ReactNode } from "react";

import "@/i18n";
import { ApiErrorClass } from "@/lib/api";

function isAbortLike(err: unknown): boolean {
  return err instanceof DOMException && (err.name === "AbortError" || err.name === "TimeoutError");
}

export function AppProviders({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        queryCache: new QueryCache({
          // A11 — errores globales: sin sistema de toasts en la app, se
          // registran en consola (los 401/aborts ya tienen manejo propio).
          onError: (error, query) => {
            if (isAbortLike(error)) return;
            if (error instanceof ApiErrorClass && error.status === 401) return;
            console.error("[query]", query.queryKey, error);
          },
        }),
        mutationCache: new MutationCache({
          onError: (error) => {
            if (isAbortLike(error)) return;
            if (error instanceof ApiErrorClass && error.status === 401) return;
            console.error("[mutation]", error);
          },
        }),
        defaultOptions: {
          queries: {
            retry: 1,
            refetchOnWindowFocus: false,
            staleTime: 30_000,
          },
        },
      })
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}