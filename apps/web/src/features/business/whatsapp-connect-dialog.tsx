import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { sileo } from "sileo";
import {
  AlertTriangle,
  Check,
  Copy,
  Link2,
  MessageCircle,
  RefreshCw,
  ShieldCheck,
  Unplug,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Segmented } from "@/components/ui/segmented";
import {
  queryKeys,
  useWhatsAppEmbeddedConfig,
  useWhatsAppEmbeddedSignup,
} from "@/hooks/use-queries";
import { api, ApiErrorClass, BASE_URL } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { WhatsAppConfig } from "@/lib/types";



/** URL pública del webhook que se pega en el panel de Meta. */
function buildWebhookUrl(): string {
  const path = `${BASE_URL}/business/whatsapp/webhook/`;
  if (BASE_URL.startsWith("http")) return path;
  return `${window.location.origin}${path}`;
}

type MetaSdk = {
  init: (opts: Record<string, unknown>) => void;
  login: (
    cb: (response: { authResponse?: { code?: string } }) => void,
    opts: Record<string, unknown>
  ) => void;
};

declare global {
  interface Window {
    FB?: MetaSdk;
    fbAsyncInit?: () => void;
  }
}

const META_SDK_SRC = "https://connect.facebook.net/es_LA/sdk.js";
const META_API_VERSION = "v21.0";

/** Carga el SDK de Meta una sola vez y lo inicializa con el App ID. */
function loadMetaSdk(appId: string): Promise<MetaSdk> {
  if (window.FB) return Promise.resolve(window.FB);
  return new Promise((resolve, reject) => {
    window.fbAsyncInit = () => {
      window.FB?.init({ appId, cookie: true, xfbml: true, version: META_API_VERSION });
      if (window.FB) resolve(window.FB);
      else reject(new Error("Meta SDK no disponible"));
    };
    if (document.getElementById("facebook-jssdk")) return;
    const script = document.createElement("script");
    script.id = "facebook-jssdk";
    script.src = META_SDK_SRC;
    script.async = true;
    script.defer = true;
    script.onerror = () => reject(new Error("No se pudo cargar Meta SDK"));
    document.body.appendChild(script);
  });
}

const LABEL_CLASS = "mb-1 block text-sm font-medium text-on-surface";
const TEXTAREA_CLASS =
  "h-auto w-full rounded-xl border border-glass-border bg-glass-surface px-3 py-2.5 text-base text-on-surface shadow-sm outline-none backdrop-blur-md focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 md:text-sm";

/** Fila de solo lectura con botón de copiar (webhook URL / verify token). */
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
        <code className="flex-1 min-w-0 overflow-x-auto whitespace-nowrap rounded-xl border border-glass-border bg-glass-surface px-3 py-2.5 text-xs text-on-surface-variant">
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

export function WhatsAppConnectDialog({
  open,
  onOpenChange,
  config,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: WhatsAppConfig | undefined;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const connected = Boolean(config?.connected);

  const [mode, setMode] = useState<"manual" | "existing">("existing");
  const [phoneNumberId, setPhoneNumberId] = useState("");
  const [displayNumber, setDisplayNumber] = useState("");
  const [wabaId, setWabaId] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [linkingMeta, setLinkingMeta] = useState(false);
  const [coexistenceConsent, setCoexistenceConsent] = useState(false);

  const sessionRef = useRef<{
    wabaId?: string;
    phoneNumberId?: string;
    onBizApp?: boolean;
  }>({});

  /** Código de autorización pendiente del callback FB.login, a la espera del postMessage. */
  const pendingCodeRef = useRef<string | null>(null);

  /** Timeout para detectar si postMessage no llega (popup cerrado, red, etc.). */
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const embeddedConfig = useWhatsAppEmbeddedConfig();
  const exchange = useWhatsAppEmbeddedSignup();

  // Al abrir se precargan los datos no secretos de la conexión existente.
  useEffect(() => {
    if (!open) return;
    setPhoneNumberId(config?.phone_number_id ?? "");
    setDisplayNumber(config?.display_phone_number ?? "");
    setWabaId(config?.waba_id ?? "");
    setAccessToken("");
    setAppSecret("");
    setMode(config?.connected && config.connection_method === "manual" ? "manual" : "existing");
    setLinkingMeta(false);
    setCoexistenceConsent(false);
    sessionRef.current = {};
    pendingCodeRef.current = null;
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
  }, [open, config]);

  // Precarga el SDK de Meta mientras el modal está abierto para que FB.login se ejecute sin retraso
  // y el navegador no bloquee la ventana emergente (user gesture preservation).
  useEffect(() => {
    if (open && embeddedConfig.data?.app_id) {
      void loadMetaSdk(embeddedConfig.data.app_id);
    }
  }, [open, embeddedConfig.data?.app_id]);

  // Meta envía los datos de la sesión de Embedded Signup por postMessage con validación estricta de origen.
  useEffect(() => {
    if (!open) return;
    const onMessage = (event: MessageEvent) => {
      if (!event.origin || !/^https:\/\/([a-zA-Z0-9-]+\.)*facebook\.com$/i.test(event.origin)) return;
      let data: Record<string, unknown> | null = null;
      try {
        data = typeof event.data === "string" ? JSON.parse(event.data) : event.data;
      } catch {
        return;
      }
      if (data && typeof data === "object" && (data as Record<string, unknown>).type === "WA_EMBEDDED_SIGNUP") {
        const payloadData = ((data as Record<string, unknown>).data || {}) as Record<string, unknown>;
        const wId = payloadData.waba_id || payloadData.wabaId;
        const pId = payloadData.phone_number_id || payloadData.phoneNumberId;
        if (wId) sessionRef.current.wabaId = String(wId);
        if (pId) sessionRef.current.phoneNumberId = String(pId);
        const onBiz = payloadData.is_on_biz_app ?? payloadData.isOnBizApp;
        if (onBiz !== undefined) {
          sessionRef.current.onBizApp = onBiz === true || onBiz === "true";
        }

        // Si ya tenemos el código del callback FB.login, ejecutar exchange ahora
        // que ambos datos (code + session info) están disponibles.
        if (pendingCodeRef.current) {
          const code = pendingCodeRef.current;
          pendingCodeRef.current = null;

          // Limpiar timeout de seguridad
          if (timeoutRef.current) clearTimeout(timeoutRef.current);

          // Validación de seguridad: asegurar que Meta envió los IDs críticos
          if (!sessionRef.current.wabaId || !sessionRef.current.phoneNumberId) {
            setLinkingMeta(false);
            sileo.error({ title: t("chats.connectDialog.missingSessionData") });
            return;
          }

          exchange.mutate(
            {
              code,
              waba_id: sessionRef.current.wabaId,
              phone_number_id: sessionRef.current.phoneNumberId,
              connection_method: sessionRef.current.onBizApp
                ? "coexistence"
                : "embedded_signup",
            },
            {
              onSuccess: () => {
                setLinkingMeta(false);
                void queryClient.invalidateQueries({ queryKey: queryKeys.whatsappConfig });
                sileo.success({ title: t("chats.connectDialog.existingSuccess") });
                onOpenChange(false);
              },
              onError: (err) => {
                setLinkingMeta(false);
                const msg =
                  err instanceof ApiErrorClass ? err.message : t("chats.connectDialog.existingError");
                sileo.error({ title: msg });
              },
            }
          );
        }
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [open, exchange, queryClient, onOpenChange, t]);

  const syncStatus = useMutation({
    mutationFn: () => api.post<WhatsAppConfig>("/business/whatsapp/sync-status/", {}),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.whatsappConfig });
      sileo.success({ title: t("chats.connectDialog.syncStatusSuccess") });
    },
    onError: (err) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("errors.generic");
      sileo.error({ title: msg });
    },
  });

  const retrySubscribe = useMutation({
    mutationFn: () =>
      api.post<{ subscribed: boolean }>("/business/whatsapp/subscribe-webhook/", {}),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.whatsappConfig });
      sileo.success({ title: t("chats.connectDialog.retrySubscribeSuccess") });
    },
    onError: (err) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("errors.generic");
      sileo.error({ title: msg });
    },
  });

  const save = useMutation({
    mutationFn: () => {
      const payload: Record<string, unknown> = { phone_number_id: phoneNumberId.trim() };
      if (displayNumber.trim()) payload.display_phone_number = displayNumber.trim();
      if (wabaId.trim()) payload.waba_id = wabaId.trim();
      // Los secretos solo se envían si el usuario los escribió: al omitirlos se
      // conservan los actuales (el backend los guarda cifrados).
      if (accessToken.trim()) payload.access_token = accessToken.trim();
      if (appSecret.trim()) payload.app_secret = appSecret.trim();
      return api.post<WhatsAppConfig>("/business/whatsapp/config/", payload);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.whatsappConfig });
      setAccessToken("");
      setAppSecret("");
      sileo.success({ title: t("chats.connectDialog.saved") });
    },
    onError: (err) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("errors.generic");
      sileo.error({ title: msg });
    },
  });

  const disconnect = useMutation({
    mutationFn: () => api.delete("/business/whatsapp/config/"),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.whatsappConfig });
      onOpenChange(false);
      sileo.success({ title: t("chats.connectDialog.disconnected") });
    },
    onError: (err) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("errors.generic");
      sileo.error({ title: msg });
    },
  });

  const startMetaSignup = async () => {
    const meta = embeddedConfig.data;
    if (!meta?.configured || !meta.app_id || !meta.config_id) {
      sileo.error({ title: t("chats.connectDialog.existingNotConfigured") });
      return;
    }
    setLinkingMeta(true);
    try {
      const FB = await loadMetaSdk(meta.app_id);
      FB.login(
        (response) => {
          if (!response?.authResponse) {
            // Usuario cerró el popup o canceló el flujo
            setLinkingMeta(false);
            pendingCodeRef.current = null;
            if (timeoutRef.current) clearTimeout(timeoutRef.current);
            return;
          }
          const code = response.authResponse?.code;
          if (!code) {
            setLinkingMeta(false);
            sileo.error({ title: t("chats.connectDialog.existingError") });
            return;
          }
          // Guardar el código y esperar al postMessage con los datos de sesión
          pendingCodeRef.current = code;

          // Timeout de seguridad: si postMessage no llega en 15s, limpiar estado
          if (timeoutRef.current) clearTimeout(timeoutRef.current);
          timeoutRef.current = setTimeout(() => {
            if (pendingCodeRef.current) {
              pendingCodeRef.current = null;
              setLinkingMeta(false);
              sileo.error({ title: t("chats.connectDialog.timeoutSessionData") });
            }
          }, 15000);
        },
        {
          config_id: meta.config_id,
          response_type: "code",
          override_default_response_type: true,
          extras: { setup: {}, featureType: "", sessionInfoVersion: "3" },
        }
      );
    } catch {
      setLinkingMeta(false);
      sileo.error({ title: t("chats.connectDialog.popupBlocked") });
    }
  };

  const canSave = phoneNumberId.trim().length > 0 && !save.isPending;
  const webhookUrl = buildWebhookUrl();
  const methodLabel =
    config?.connection_method === "embedded_signup"
      ? t("chats.connectDialog.methodEmbedded")
      : config?.connection_method === "coexistence"
        ? t("chats.connectDialog.methodCoexistence")
        : t("chats.connectDialog.methodManual");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/15">
              <MessageCircle className="h-5 w-5 text-primary" />
            </span>
            {t("chats.connectDialog.title")}
          </DialogTitle>
          <DialogDescription>
            {mode === "existing"
              ? t("chats.connectDialog.existingSubtitle")
              : t("chats.connectDialog.manualSubtitle")}
          </DialogDescription>
        </DialogHeader>

        {!connected && (
          <Segmented
            layoutId="whatsapp-connect-mode"
            value={mode}
            onChange={setMode}
            options={[
              { value: "manual", label: t("chats.connectDialog.modeManual") },
              { value: "existing", label: t("chats.connectDialog.modeExisting") },
            ]}
          />
        )}

        {mode === "manual" ? (
          <div className="space-y-4">
            <label className="block">
              <span className={LABEL_CLASS}>{t("chats.connectDialog.phoneNumberId")}</span>
              <Input
                value={phoneNumberId}
                onChange={(e) => setPhoneNumberId(e.target.value)}
                placeholder={t("chats.connectDialog.phoneNumberIdPlaceholder")}
                autoComplete="off"
              />
              <span className="mt-1 block text-xs text-on-surface-variant">
                {t("chats.connectDialog.phoneNumberIdHint")}
              </span>
            </label>

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block">
                <span className={LABEL_CLASS}>{t("chats.connectDialog.displayNumber")}</span>
                <Input
                  value={displayNumber}
                  onChange={(e) => setDisplayNumber(e.target.value)}
                  placeholder={t("chats.connectDialog.displayNumberPlaceholder")}
                  autoComplete="off"
                />
              </label>
              <label className="block">
                <span className={LABEL_CLASS}>{t("chats.connectDialog.wabaId")}</span>
                <Input
                  value={wabaId}
                  onChange={(e) => setWabaId(e.target.value)}
                  placeholder={t("chats.connectDialog.wabaIdPlaceholder")}
                  autoComplete="off"
                />
              </label>
            </div>

            <label className="block">
              <span className={LABEL_CLASS}>{t("chats.connectDialog.accessToken")}</span>
              <textarea
                value={accessToken}
                onChange={(e) => setAccessToken(e.target.value)}
                rows={2}
                placeholder={
                  connected
                    ? t("chats.connectDialog.secretHint")
                    : t("chats.connectDialog.accessTokenPlaceholder")
                }
                className={TEXTAREA_CLASS}
              />
            </label>

            <label className="block">
              <span className={LABEL_CLASS}>{t("chats.connectDialog.appSecret")}</span>
              <textarea
                value={appSecret}
                onChange={(e) => setAppSecret(e.target.value)}
                rows={2}
                placeholder={
                  connected
                    ? t("chats.connectDialog.secretHint")
                    : t("chats.connectDialog.appSecretPlaceholder")
                }
                className={TEXTAREA_CLASS}
              />
            </label>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-2 rounded-xl border border-glass-border bg-glass-surface/60 p-4">
              <p className="text-sm text-on-surface">
                {t("chats.connectDialog.existingIntro")}
              </p>
              <p className="text-xs text-on-surface-variant">
                {t("chats.connectDialog.existingRequirements")}
              </p>
            </div>
            {embeddedConfig.data && !embeddedConfig.data.configured && (
              <p className="rounded-xl border border-error/30 bg-error/10 p-3 text-xs text-error">
                {t("chats.connectDialog.existingNotConfigured")}
              </p>
            )}

            {/* Consentimiento obligatorio de Coexistence antes de conectar */}
            <label className="flex items-start gap-2.5 rounded-xl border border-glass-border bg-glass-surface/60 p-3 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={coexistenceConsent}
                onChange={(e) => setCoexistenceConsent(e.target.checked)}
                className="mt-0.5 h-4 w-4 accent-primary shrink-0"
              />
              <span className="text-xs text-on-surface-variant leading-relaxed">
                {t("chats.connectDialog.coexistenceConsent")}
              </span>
            </label>
            {!coexistenceConsent && (
              <p className="text-xs text-on-surface-variant/70 italic">
                {t("chats.connectDialog.coexistenceConsentRequired")}
              </p>
            )}

            <Button
              type="button"
              variant="glow"
              className="w-full"
              onClick={() => void startMetaSignup()}
              disabled={
                linkingMeta ||
                exchange.isPending ||
                embeddedConfig.isLoading ||
                !embeddedConfig.data?.configured ||
                !coexistenceConsent
              }
            >
              <Link2 className="h-4 w-4" />
              {linkingMeta || exchange.isPending
                ? t("chats.connectDialog.connectingMeta")
                : t("chats.connectDialog.connectMeta")}
            </Button>
          </div>
        )}

        {connected && config?.verify_token && (
          <div className="space-y-3 rounded-xl border border-glass-border bg-glass-surface/60 p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-medium text-on-surface">
                {t("chats.connectDialog.webhookTitle")}
              </p>
              <span className="rounded-full bg-primary/15 px-2 py-0.5 text-xs font-medium text-primary">
                {t("chats.connectDialog.connectedVia", { method: methodLabel })}
              </span>
            </div>
            <CopyField
              label={t("chats.connectDialog.webhookUrl")}
              value={webhookUrl}
            />
            <CopyField
              label={t("chats.connectDialog.verifyToken")}
              value={config.verify_token}
            />
            <p className="text-xs text-on-surface-variant">
              {t("chats.connectDialog.steps")}
            </p>
          </div>
        )}

        {/* ── Alertas de seguridad: token expirado / webhook no suscrito ── */}
        {connected && config?.token_valid === false && (
          <div className="flex items-center gap-2 rounded-xl border border-amber-400/30 bg-amber-500/10 p-3">
            <AlertTriangle className="h-4 w-4 shrink-0 text-amber-500" />
            <p className="text-xs text-amber-700 dark:text-amber-300">
              {t("chats.connectDialog.tokenExpiredWarning")}
            </p>
          </div>
        )}

        {connected && config?.webhook_subscribed === false && (
          <div className="flex items-center gap-2 rounded-xl border border-amber-400/30 bg-amber-500/10 p-3">
            <AlertTriangle className="h-4 w-4 shrink-0 text-amber-500" />
            <div className="flex flex-1 items-center justify-between gap-2">
              <p className="text-xs text-amber-700 dark:text-amber-300">
                {t("chats.connectDialog.webhookNotSubscribedWarning")}
              </p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => retrySubscribe.mutate()}
                disabled={retrySubscribe.isPending}
                className="shrink-0 text-xs"
              >
                <RefreshCw className={cn("h-3 w-3", retrySubscribe.isPending && "animate-spin")} />
                {retrySubscribe.isPending
                  ? t("chats.connectDialog.retryingSubscribe")
                  : t("chats.connectDialog.retrySubscribe")}
              </Button>
            </div>
          </div>
        )}

        {/* ── Panel de salud: estado detallado de la conexión ── */}
        {connected && (
          <div className="space-y-2 rounded-xl border border-glass-border bg-glass-surface/60 p-3">
            <div className="flex items-center justify-between gap-2">
              <h4 className="flex items-center gap-1.5 text-sm font-medium text-on-surface">
                <ShieldCheck className="h-4 w-4 text-primary" />
                {t("chats.connectDialog.healthTitle")}
              </h4>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => syncStatus.mutate()}
                disabled={syncStatus.isPending}
                className="text-xs"
              >
                <RefreshCw className={cn("h-3 w-3", syncStatus.isPending && "animate-spin")} />
                {syncStatus.isPending
                  ? t("chats.connectDialog.syncingStatus")
                  : t("chats.connectDialog.syncStatus")}
              </Button>
            </div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <dt className="text-on-surface-variant">{t("chats.connectDialog.healthStatus")}</dt>
              <dd className={cn(
                "font-medium",
                config?.onboarding_status === "reconnect_required" ? "text-amber-500" : "text-primary"
              )}>
                {config?.onboarding_status === "reconnect_required"
                  ? t("chats.connectDialog.healthStatusNeedsReconnect")
                  : t("chats.connectDialog.healthStatusActive")}
              </dd>

              {config?.verified_name && (
                <>
                  <dt className="text-on-surface-variant">{t("chats.connectDialog.healthVerifiedName")}</dt>
                  <dd className="text-on-surface">{config.verified_name}</dd>
                </>
              )}

              {config?.quality_rating && (
                <>
                  <dt className="text-on-surface-variant">{t("chats.connectDialog.healthQuality")}</dt>
                  <dd className="text-on-surface">{config.quality_rating}</dd>
                </>
              )}

              {config?.messaging_limit_tier && (
                <>
                  <dt className="text-on-surface-variant">{t("chats.connectDialog.healthTier")}</dt>
                  <dd className="text-on-surface">{config.messaging_limit_tier}</dd>
                </>
              )}

              <dt className="text-on-surface-variant">{t("chats.connectDialog.healthWebhook")}</dt>
              <dd className={cn(
                "font-medium",
                config?.webhook_subscribed ? "text-primary" : "text-amber-500"
              )}>
                {config?.webhook_subscribed
                  ? t("chats.connectDialog.healthWebhookActive")
                  : t("chats.connectDialog.healthWebhookPending")}
              </dd>
            </dl>
          </div>
        )}

        {/* ── Botón de reconexión cuando el token ha expirado ── */}
        {connected && (config?.token_valid === false || config?.onboarding_status === "reconnect_required") && (
          <Button
            type="button"
            variant="glow"
            className="w-full"
            onClick={() => void startMetaSignup()}
            disabled={linkingMeta || exchange.isPending || embeddedConfig.isLoading}
          >
            <RefreshCw className={cn("h-4 w-4", linkingMeta && "animate-spin")} />
            {linkingMeta || exchange.isPending
              ? t("chats.connectDialog.reconnecting")
              : t("chats.connectDialog.reconnect")}
          </Button>
        )}

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
              {t("chats.connectDialog.disconnect")}
            </Button>
          ) : (
            <span />
          )}
          <div className="flex gap-2 sm:justify-end">
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              disabled={save.isPending}
            >
              {t("common.cancel")}
            </Button>
            {mode === "manual" && (
              <Button
                type="button"
                variant="glow"
                onClick={() => save.mutate()}
                disabled={!canSave}
              >
                {save.isPending
                  ? t("chats.connectDialog.saving")
                  : t("chats.connectDialog.save")}
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
