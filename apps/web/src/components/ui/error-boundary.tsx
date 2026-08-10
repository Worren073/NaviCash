import { Component, type ErrorInfo, type ReactNode } from "react";

import { useTranslation } from "react-i18next";

function ErrorBoundaryFallback() {
  const { t } = useTranslation();
  return (
    <div
      role="alert"
      className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center"
    >
      <div className="flex h-16 w-16 items-center justify-center rounded-3xl bg-primary text-3xl font-bold text-on-primary shadow-lg shadow-primary/30">
        N
      </div>
      <h1 className="text-xl font-semibold text-on-surface">{t("errors.crash")}</h1>
      <button
        type="button"
        onClick={() => window.location.reload()}
        className="rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-on-primary transition-colors hover:opacity-90"
      >
        {t("common.retry")}
      </button>
    </div>
  );
}

/**
 * Error boundary raíz (A11): evita la pantalla blanca ante errores de render
 * y ofrece recargar la aplicación.
 */
export class ErrorBoundary extends Component<{ children?: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary:", error, info);
  }

  render() {
    if (this.state.hasError) return <ErrorBoundaryFallback />;
    return this.props.children;
  }
}