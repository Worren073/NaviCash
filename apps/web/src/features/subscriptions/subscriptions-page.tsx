import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { CalendarRange, Plus, Trash2 } from "lucide-react";

import { useSubscriptions, queryKeys } from "@/hooks/use-queries";
import { api, ApiErrorClass } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SUBSCRIPTION_COLORS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import type { Subscription, SubscriptionStatus } from "@/lib/types";

const STATUS_CLS: Record<SubscriptionStatus, string> = {
  activa: "bg-emerald-500/15 text-emerald-600",
  proxima: "bg-sky-500/15 text-sky-600",
  finalizada: "bg-surface-container-high text-on-surface-variant",
};

function toISODate(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function formatRange(isoStart: string, isoEnd: string): string {
  const fmt = (iso: string) =>
    new Date(iso).toLocaleDateString("es-VE", { day: "2-digit", month: "short", year: "numeric" });
  return `${fmt(isoStart)} → ${fmt(isoEnd)}`;
}

function SubscriptionCard({ sub }: { sub: Subscription }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const color = sub.color || SUBSCRIPTION_COLORS[0];
  const pct = Number(sub.progress_percent);

  const remove = useMutation({
    mutationFn: () => api.delete(`/subscriptions/${sub.id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.subscriptions });
    },
  });

  return (
    <div className="glass-card rounded-xl bg-surface p-4">
      <div className="mb-4 flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div
            className="flex h-10 w-10 items-center justify-center rounded-full border"
            style={{
              backgroundColor: `${color}1a`,
              borderColor: `${color}40`,
            }}
          >
            <CalendarRange className="h-5 w-5" style={{ color }} />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-on-surface">{sub.name}</h3>
            <p className="text-xs text-on-surface-variant">{formatRange(sub.start_date, sub.end_date)}</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-semibold", STATUS_CLS[sub.status])}>
            {t(`subscriptions.status${sub.status.charAt(0).toUpperCase()}${sub.status.slice(1)}`)}
          </span>
          <button
            type="button"
            aria-label={t("common.delete")}
            onClick={() => remove.mutate()}
            disabled={remove.isPending}
            className="rounded-full p-1.5 text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-status-delayed"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="mb-1.5 flex items-end justify-between">
        <span className="text-sm font-medium text-on-surface-variant">
          {t("subscriptions.progress", {
            percent: pct.toFixed(1),
            elapsed: sub.days_elapsed,
            total: sub.days_total,
          })}
        </span>
        <span className="text-sm font-bold" style={{ color }}>
          {pct.toFixed(1)}%
        </span>
      </div>
      <div className="h-2.5 overflow-hidden rounded-full bg-surface-container-highest">
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${Math.min(100, pct)}%`,
            backgroundColor: color,
            boxShadow: `0 0 8px ${color}66`,
          }}
        />
      </div>
    </div>
  );
}

function NewSubscriptionDialog() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [color, setColor] = useState<string>(SUBSCRIPTION_COLORS[0]);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [today30, setToday30] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => {
      const start = today30 ? toISODate(new Date()) : startDate;
      const end = today30 ? toISODate(new Date(Date.now() + 30 * 86_400_000)) : endDate;
      return api.post<Subscription>("/subscriptions", {
        name: name.trim(),
        color,
        start_date: start,
        end_date: end,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.subscriptions });
      setOpen(false);
      setName("");
      setColor(SUBSCRIPTION_COLORS[0]);
      setStartDate("");
      setEndDate("");
      setToday30(true);
      setError(null);
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) {
        setError(err.fieldErrors?.end_date?.[0] ?? err.fieldErrors?.start_date?.[0] ?? err.message);
      } else {
        setError(t("errors.generic"));
      }
    },
  });

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-2 flex w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-outline bg-surface-container-low py-4 transition-colors hover:bg-surface-container-high"
      >
        <Plus className="h-7 w-7 text-primary" />
        <span className="text-sm font-medium text-on-surface-variant">{t("subscriptions.newOne")}</span>
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("subscriptions.newOne")}</DialogTitle>
            <DialogDescription>{t("subscriptions.subtitle")}</DialogDescription>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              setError(null);
              create.mutate();
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="sub-name">{t("subscriptions.name")}</Label>
              <Input
                id="sub-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("subscriptions.namePlaceholder")}
                maxLength={120}
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label>{t("subscriptions.color")}</Label>
              <div className="flex flex-wrap gap-2">
                {SUBSCRIPTION_COLORS.map((c) => (
                  <button
                    key={c}
                    type="button"
                    aria-label={c}
                    onClick={() => setColor(c)}
                    className={cn(
                      "h-8 w-8 rounded-full border-2 transition-all",
                      color === c ? "scale-110 border-on-surface" : "border-transparent opacity-80 hover:opacity-100"
                    )}
                    style={{ backgroundColor: c }}
                  />
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="sub-start">{t("subscriptions.startDate")}</Label>
                <Input
                  id="sub-start"
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  disabled={today30}
                  required={!today30}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="sub-end">{t("subscriptions.endDate")}</Label>
                <Input
                  id="sub-end"
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  disabled={today30}
                  required={!today30}
                />
              </div>
            </div>

            <label className="flex cursor-pointer items-center gap-2.5 text-sm text-on-surface">
              <input
                type="checkbox"
                checked={today30}
                onChange={(e) => setToday30(e.target.checked)}
                className="h-4 w-4 accent-primary"
              />
              <span>
                {t("subscriptions.today30")}
                <span className="block text-xs text-on-surface-variant">
                  {t("subscriptions.today30Hint")}
                </span>
              </span>
            </label>

            {error && (
              <p className="rounded-lg bg-error-container/60 px-3 py-2 text-sm text-on-error-container">
                {error}
              </p>
            )}

            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setOpen(false)}
                disabled={create.isPending}
              >
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={create.isPending}>
                {create.isPending ? t("common.loading") : t("common.save")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

export default function SubscriptionsPage() {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useSubscriptions();

  return (
    <div className="mt-4 space-y-6">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
            <CalendarRange size={20} className="text-primary" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-on-surface">{t("subscriptions.title")}</h2>
            <p className="text-sm text-on-surface-variant">{t("subscriptions.subtitle")}</p>
          </div>
        </div>
      </div>

      {isError ? (
        <p className="glass-panel rounded-lg p-6 text-center text-sm text-on-surface-variant">
          {t("errors.generic")}
        </p>
      ) : isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
      ) : (data ?? []).length === 0 ? (
        <p className="glass-panel rounded-lg p-6 text-center text-sm text-on-surface-variant">
          {t("subscriptions.empty")}
        </p>
      ) : (
        <div className="space-y-2">
          {(data ?? []).map((sub) => (
            <SubscriptionCard key={sub.id} sub={sub} />
          ))}
        </div>
      )}

      <NewSubscriptionDialog />
    </div>
  );
}