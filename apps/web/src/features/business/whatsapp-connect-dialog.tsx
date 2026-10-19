import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { sileo } from "sileo";
import { Check, Copy, MessageCircle, Unplug } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { queryKeys } from "@/hooks/use-queries";
import { api, ApiErrorClass, BASE_URL } from "@/lib/api";
import type { WhatsAppConfig } from "@/lib/types";

/** URL pública del webhook que se pega en el panel de Meta. */
function buildWebhookUrl(): string {
  const path = `${BASE_URL}/business/whatsapp/webhook/`;
  if (BASE_URL.startsWith("http")) return path;
  return `${window.location.origin}${path}`;
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

  const [phoneNumberId, setPhoneNumberId] = useState("");
  const [displayNumber, setDisplayNumber] = useState("");
  const [wabaId, setWabaId] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [appSecret, setAppSecret] = useState("");

  // Al abrir se precargan los datos no secretos de la conexión existente.
  useEffect(() => {
    if (!open) return;
    setPhoneNumberId(config?.phone_number_id ?? "");
    setDisplayNumber(config?.display_phone_number ?? "");
    setWabaId(config?.waba_id ?? "");
    setAccessToken("");
    setAppSecret("");
  }, [open, config]);

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

  const canSave = phoneNumberId.trim().length > 0 && !save.isPending;
  const webhookUrl = buildWebhookUrl();

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
          <DialogDescription>{t("chats.connectDialog.subtitle")}</DialogDescription>
        </DialogHeader>

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

          {connected && config?.verify_token && (
            <div className="space-y-3 rounded-xl border border-glass-border bg-glass-surface/60 p-3">
              <p className="text-sm font-medium text-on-surface">
                {t("chats.connectDialog.webhookTitle")}
              </p>
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
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
