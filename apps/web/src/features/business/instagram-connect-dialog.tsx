import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { sileo } from "sileo";
import { AlertTriangle, Check, Copy, Instagram, Unplug } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { queryKeys } from "@/hooks/use-queries";
import { api, ApiErrorClass, BASE_URL } from "@/lib/api";
import type { InstagramConfig, InstagramOAuthStart } from "@/lib/types";

/** URL pública del webhook de Instagram que se pega en el panel de Meta. */
function buildWebhookUrl(): string {
  const path = `${BASE_URL}/business/instagram/webhook/`;
  if (BASE_URL.startsWith("http")) return path;
  return `${window.location.origin}${path}`;
}

const LABEL_CLASS = "mb-1 block text-sm font-medium text-on-surface";

/** Fila de solo lectura con botón de copiar (URL del webhook). */
function CopyField({ label, value }: { label: string; value: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1_500);
    } catch {
      sileo.error({ title: t("errors.generic") });
    }
  };

  return (
    <div>
      <span className={LABEL_CLASS}>{label}</span>
      <div className="flex items-stretch gap-2">
        <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap rounded-xl border border-glass-border bg-glass-surface px-3 py-2.5 text-xs text-on-surface-variant">
          {value}
        </code>
        <Button
          type="button"
          variant="outline"
          size="icon"
          onClick={copy}
          aria-label={t("chats.connectDialog.copy")}
        >
          {copied ? <Check className="h-4 w-4 text-primary" /> : <Copy className="h-4 w-4" />}
        </Button>
      </div>
    </div>
  );
}

export function InstagramConnectDialog({
  open,
  onOpenChange,
  config,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: InstagramConfig | undefined;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const connected = Boolean(config?.connected);
  const [popupBlocked, setPopupBlocked] = useState(false);

  const popupRef = useRef<Window | null>(null);
  const pollRef = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => () => stopPolling(), [stopPolling]);

  const start = useMutation({
    // `mode=popup` hace que el callback cierre solo la ventana emergente;
    // `mode=page` mantiene la redirección de página completa (móvil/fallback).
    mutationFn: (mode: "popup" | "page") =>
      api.get<InstagramOAuthStart>(`/business/instagram/oauth/start/?mode=${mode}`),
  });

  const reportError = useCallback(
    (err: unknown) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("errors.generic");
      sileo.error({ title: msg });
    },
    [t]
  );

  const redirectToInstagram = useCallback(() => {
    start.mutate("page", {
      onSuccess: (data) => {
        if (!data.authorize_url) {
          sileo.error({ title: t("chats.instagramDialog.notConfigured") });
          return;
        }
        window.location.assign(data.authorize_url);
      },
      onError: reportError,
    });
  }, [start, t, reportError]);

  const refreshStatus = useCallback(() => {
    void (async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.instagramConfig });
      const cfg = queryClient.getQueryData<InstagramConfig>(queryKeys.instagramConfig);
      if (cfg?.connected) {
        sileo.success({ title: t("chats.instagramDialog.success") });
      } else {
        sileo.info({ title: t("chats.instagramDialog.cancelled") });
      }
    })();
  }, [queryClient, t]);

  const handleConnect = useCallback(() => {
    setPopupBlocked(false);
    // En pantallas táctiles el popup se abre como pestaña y no se autocierra:
    // se usa la redirección de página completa.
    const coarsePointer = window.matchMedia?.("(pointer: coarse)").matches ?? false;
    if (coarsePointer) {
      redirectToInstagram();
      return;
    }

    // Ventana emergente abierta de forma síncrona (evita el bloqueador de popups).
    const popup = window.open(
      "about:blank",
      "navicash-instagram-oauth",
      "width=600,height=740"
    );
    if (!popup) {
      // El navegador bloqueó la ventana: se avisa y se ofrece continuar aquí.
      setPopupBlocked(true);
      return;
    }
    // Se corta el acceso al opener por seguridad: la app detecta el cierre.
    popup.opener = null;
    popupRef.current = popup;

    start.mutate("popup", {
      onSuccess: (data) => {
        if (!data.authorize_url) {
          popup.close();
          popupRef.current = null;
          sileo.error({ title: t("chats.instagramDialog.notConfigured") });
          return;
        }
        popup.location.href = data.authorize_url;
        stopPolling();
        pollRef.current = window.setInterval(() => {
          if (popupRef.current?.closed) {
            stopPolling();
            popupRef.current = null;
            refreshStatus();
          }
        }, 600);
      },
      onError: (err) => {
        popup.close();
        popupRef.current = null;
        reportError(err);
      },
    });
  }, [redirectToInstagram, start, stopPolling, refreshStatus, reportError, t]);

  const disconnect = useMutation({
    mutationFn: () => api.delete("/business/instagram/config/"),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.instagramConfig });
      onOpenChange(false);
      sileo.success({ title: t("chats.instagramDialog.disconnected") });
    },
    onError: (err) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("errors.generic");
      sileo.error({ title: msg });
    },
  });

  const webhookUrl = buildWebhookUrl();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/15">
              <Instagram className="h-5 w-5 text-primary" />
            </span>
            {t("chats.instagramDialog.title")}
          </DialogTitle>
          <DialogDescription>{t("chats.instagramDialog.subtitle")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {connected ? (
            <>
              <div className="rounded-xl border border-glass-border bg-glass-surface/60 p-3">
                <span className={LABEL_CLASS}>{t("chats.instagramDialog.account")}</span>
                <p className="text-sm text-on-surface">
                  {config?.username ? `@${config.username}` : config?.ig_user_id}
                </p>
              </div>

              <div className="space-y-3 rounded-xl border border-glass-border bg-glass-surface/60 p-3">
                <p className="text-sm font-medium text-on-surface">
                  {t("chats.instagramDialog.webhookTitle")}
                </p>
                <CopyField
                  label={t("chats.instagramDialog.webhookUrl")}
                  value={webhookUrl}
                />
                <p className="text-xs text-on-surface-variant">
                  {t("chats.instagramDialog.webhookUrlHint")}
                </p>
                <p className="text-xs text-on-surface-variant">
                  {t("chats.instagramDialog.steps")}
                </p>
              </div>
            </>
          ) : (
            <>
              <p className="text-sm text-on-surface-variant">
                {t("chats.instagramDialog.requirements")}
              </p>
              {popupBlocked && (
                <div className="rounded-xl border border-status-warning/40 bg-status-warning/10 p-3">
                  <p className="flex items-start gap-2 text-sm text-on-surface">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-status-warning" />
                    <span>{t("chats.instagramDialog.popupBlocked")}</span>
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="mt-2"
                    onClick={redirectToInstagram}
                    disabled={start.isPending}
                  >
                    {t("chats.instagramDialog.popupBlockedAction")}
                  </Button>
                </div>
              )}
            </>
          )}
        </div>

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
          {connected ? (
            <Button
              type="button"
              variant="ghost"
              className="text-error"
              onClick={() => disconnect.mutate()}
              disabled={disconnect.isPending}
            >
              <Unplug className="h-4 w-4" />
              {t("chats.instagramDialog.disconnect")}
            </Button>
          ) : (
            <span />
          )}
          <div className="flex gap-2 sm:justify-end">
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              disabled={start.isPending}
            >
              {t("common.cancel")}
            </Button>
            {!connected && (
              <Button
                type="button"
                variant="glow"
                className="gap-1"
                onClick={handleConnect}
                disabled={start.isPending}
              >
                <Instagram className="h-4 w-4" />
                {start.isPending
                  ? t("chats.instagramDialog.connecting")
                  : t("chats.instagramDialog.connect")}
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
