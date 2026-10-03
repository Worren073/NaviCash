import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { sileo } from "sileo";
import { PhoneCall } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { queryKeys } from "@/hooks/use-queries";
import { api, ApiErrorClass } from "@/lib/api";
import type {
  CollectionChannel,
  CollectionFollowUp,
  CollectionOutcome,
} from "@/lib/types";

const CHANNELS: CollectionChannel[] = ["llamada", "email", "whatsapp", "visita", "otro"];
const OUTCOMES: CollectionOutcome[] = [
  "sin_respuesta",
  "promesa_pago",
  "pago_realizado",
  "rechazado",
  "otro",
];

const SELECT_CLASS =
  "h-11 w-full rounded-xl border border-glass-border bg-glass-surface px-3 text-base text-on-surface shadow-sm outline-none backdrop-blur-md focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 md:text-sm";

export function FollowUpDialog({
  open,
  onOpenChange,
  invoiceId,
  onRegistered,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  invoiceId: string;
  onRegistered?: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [channel, setChannel] = useState<CollectionChannel>("llamada");
  const [outcome, setOutcome] = useState<CollectionOutcome>("sin_respuesta");
  const [promisedDate, setPromisedDate] = useState("");
  const [notes, setNotes] = useState("");

  const needsDate = outcome === "promesa_pago";
  const canSave = !needsDate || Boolean(promisedDate);

  const register = useMutation({
    mutationFn: () => {
      const payload: Record<string, unknown> = { invoice: invoiceId, channel, outcome };
      if (needsDate) payload.promised_date = promisedDate;
      if (notes.trim()) payload.notes = notes.trim();
      return api.post<CollectionFollowUp>("/business/follow-ups/", payload);
    },
    onSuccess: () => {
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.followUps }),
        queryClient.invalidateQueries({ queryKey: queryKeys.invoices }),
      ]);
      setChannel("llamada");
      setOutcome("sin_respuesta");
      setPromisedDate("");
      setNotes("");
      onOpenChange(false);
      onRegistered?.();
      sileo.success({ title: t("collection.followUps.added") });
    },
    onError: (err) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("errors.generic");
      sileo.error({ title: msg });
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/15">
              <PhoneCall className="h-5 w-5 text-primary" />
            </span>
            {t("collection.followUps.record")}
          </DialogTitle>
          <DialogDescription>{t("collection.subtitle")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-on-surface">
              {t("collection.followUps.channel")}
            </span>
            <select
              value={channel}
              onChange={(e) => setChannel(e.target.value as CollectionChannel)}
              className={SELECT_CLASS}
            >
              {CHANNELS.map((c) => (
                <option key={c} value={c}>
                  {t(`collection.channels.${c}`)}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="mb-1 block text-sm font-medium text-on-surface">
              {t("collection.followUps.outcome")}
            </span>
            <select
              value={outcome}
              onChange={(e) => setOutcome(e.target.value as CollectionOutcome)}
              className={SELECT_CLASS}
            >
              {OUTCOMES.map((o) => (
                <option key={o} value={o}>
                  {t(`collection.outcomes.${o}`)}
                </option>
              ))}
            </select>
          </label>

          {needsDate && (
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-on-surface">
                {t("collection.followUps.promisedDate")}
              </span>
              <Input
                type="date"
                value={promisedDate}
                onChange={(e) => setPromisedDate(e.target.value)}
              />
            </label>
          )}

          <label className="block">
            <span className="mb-1 block text-sm font-medium text-on-surface">
              {t("collection.followUps.notes")}
            </span>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              placeholder={t("collection.followUps.notesPlaceholder")}
              className="h-auto w-full rounded-xl border border-glass-border bg-glass-surface px-3 py-2.5 text-base text-on-surface shadow-sm outline-none backdrop-blur-md focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 md:text-sm"
            />
          </label>
        </div>

        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={register.isPending}
          >
            {t("common.cancel")}
          </Button>
          <Button
            variant="glow"
            onClick={() => register.mutate()}
            disabled={!canSave || register.isPending}
          >
            {register.isPending
              ? t("collection.followUps.recording")
              : t("collection.followUps.record")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}