import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Plus, ShoppingBasket, Trash2 } from "lucide-react";

import { useChecklists, useOverview, useWallets, queryKeys } from "@/hooks/use-queries";
import { api, ApiErrorClass } from "@/lib/api";
import { sileo } from "sileo";
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
import { ConfirmDeleteDialog } from "@/components/ui/confirm-delete-dialog";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { formatMoney } from "@/lib/format";
import type { Checklist, ChecklistItem, Currency } from "@/lib/types";

const ESTADO_BADGE: Record<Checklist["estado"], "success" | "secondary"> = {
  en_curso: "secondary",
  completada: "success",
};

const ESTADO_LABEL: Record<Checklist["estado"], "statusEnCurso" | "statusCompletada"> = {
  en_curso: "statusEnCurso",
  completada: "statusCompletada",
};

function convertSubtotal(value: string, currency: Currency, rate: number | null): {
  usd: number;
  ves: number;
} {
  const num = Number(value) || 0;
  if (currency === "USD") {
    return { usd: num, ves: rate && rate > 0 ? num * rate : num };
  }
  return { usd: rate && rate > 0 ? num / rate : num, ves: num };
}

function PriceDialog({
  list,
  item,
  open,
  onOpenChange,
}: {
  list: Checklist;
  item: ChecklistItem;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const rate = useRate();
  const [price, setPrice] = useState(item.precio_unitario ?? "");
  const [cantidad, setCantidad] = useState(String(item.cantidad || 1));
  const [error, setError] = useState<string | null>(null);

  const parsedPrice = Number(price);
  const parsedQty = Number(cantidad);
  const priceDirty = price !== "";
  const qtyDirty = cantidad !== "";
  const priceInvalid = priceDirty && (!Number.isFinite(parsedPrice) || parsedPrice <= 0);
  const qtyInvalid = qtyDirty && (!Number.isInteger(parsedQty) || parsedQty < 1);
  const canSave = priceDirty && qtyDirty && !priceInvalid && !qtyInvalid;
  const effectivePrice = Number.isFinite(parsedPrice) && parsedPrice > 0 ? parsedPrice : 0;
  const qtyNum = Number.isInteger(parsedQty) && parsedQty >= 1 ? parsedQty : 1;
  const subtotal = (effectivePrice * qtyNum).toFixed(2);
  const converted = convertSubtotal(subtotal, list.currency, rate);

  const save = useMutation({
    mutationFn: () => {
      const items = list.items.map((x) =>
        x.id === item.id
          ? { ...x, precio_unitario: price, cantidad: qtyNum, is_checked: true }
          : x
      );
      return api.patch<Checklist>(`/checklists/${list.id}`, { items });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.checklists });
      onOpenChange(false);
      setError(null);
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) setError(err.message);
      else setError(t("errors.generic"));
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("checklists.priceTitle")}</DialogTitle>
          <DialogDescription>
            {t("checklists.priceHint", { currency: list.currency, other: list.currency === "USD" ? "VES" : "USD" })}
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            save.mutate();
          }}
        >
          <div className="flex items-baseline justify-center gap-2 rounded-2xl bg-surface-container-low px-4 py-4">
            <span className="text-lg font-bold text-on-surface">{item.name}</span>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor={`price-${item.id}`}>{t("checklists.unitPrice")}</Label>
              <Input
                id={`price-${item.id}`}
                type="number"
                inputMode="decimal"
                step="0.01"
                min="0.01"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder="0.00"
                required
                autoFocus
                aria-invalid={priceInvalid}
                aria-describedby={priceInvalid ? `price-err-${item.id}` : undefined}
                disabled={save.isPending}
              />
              {priceInvalid && (
                <p id={`price-err-${item.id}`} className="text-xs text-status-delayed">
                  {t("checklists.errorPrice")}
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={`qty-${item.id}`}>{t("checklists.quantity")}</Label>
              <Input
                id={`qty-${item.id}`}
                type="number"
                inputMode="numeric"
                step="1"
                min="1"
                value={cantidad}
                onChange={(e) => setCantidad(e.target.value)}
                required
                aria-invalid={qtyInvalid}
                aria-describedby={qtyInvalid ? `qty-err-${item.id}` : undefined}
                disabled={save.isPending}
              />
              {qtyInvalid && (
                <p id={`qty-err-${item.id}`} className="text-xs text-status-delayed">
                  {t("checklists.errorQty")}
                </p>
              )}
            </div>
          </div>

          <div className="space-y-1.5 rounded-2xl border border-glass-border bg-glass-surface px-4 py-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-on-surface-variant">{t("checklists.subtotal")}</span>
              <span className="font-semibold text-on-surface">
                {formatMoney(subtotal, list.currency, { symbol: true })}
              </span>
            </div>
            <div className="flex items-center justify-between text-xs text-on-surface-variant">
              <span>{list.currency === "USD" ? t("checklists.esVes") : t("checklists.esUsd")}</span>
              <span className="font-medium">
                {list.currency === "USD"
                  ? formatMoney(converted.ves, "VES", { symbol: true })
                  : formatMoney(converted.usd, "USD", { symbol: true })}
              </span>
            </div>
          </div>

          {error && (
            <p className="rounded-lg bg-error-container/60 px-3 py-2 text-sm text-on-error-container">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              disabled={save.isPending}
            >
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={save.isPending || !canSave}>
              {save.isPending ? t("common.loading") : t("common.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function CompleteDialog({
  list,
  open,
  onOpenChange,
}: {
  list: Checklist;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: wallets, isLoading: walletsLoading } = useWallets();
  const rate = useRate();
  const [walletId, setWalletId] = useState("");
  const [total, setTotal] = useState(list.total_estimado);
  const [error, setError] = useState<string | null>(null);

  const totalNum = Number(total);
  const totalInvalid = total.trim() === "" || !Number.isFinite(totalNum) || totalNum <= 0;
  const convertedTotal = convertSubtotal(totalInvalid ? "0" : total, list.currency, rate);
  const bigTotal = totalInvalid ? 0 : totalNum;

  const eligibleWallets = (wallets ?? []).filter((w) => w.currency === list.currency && w.tipo !== "saving");

  const complete = useMutation({
    mutationFn: () =>
      api.post<Checklist>(`/checklists/${list.id}/complete`, {
        wallet: walletId,
        total_real: total,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.checklists });
      void queryClient.invalidateQueries({ queryKey: queryKeys.wallets });
      void queryClient.invalidateQueries({ queryKey: queryKeys.overview });
      void queryClient.invalidateQueries({ queryKey: queryKeys.transactions });
      sileo.success({ title: t("checklists.completed") });
      onOpenChange(false);
      setError(null);
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) setError(err.message);
      else setError(t("errors.generic"));
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("checklists.completeTitle")}</DialogTitle>
          <DialogDescription>{t("checklists.completeHint")}</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            complete.mutate();
          }}
        >
          <div className="space-y-2 rounded-2xl border border-glass-border bg-glass-surface px-4 py-3">
            <p className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
              {t("checklists.receipt")}
            </p>
            <ul className="space-y-1.5">
              {list.items.map((it) => (
                <li key={it.id} className="flex items-baseline justify-between gap-2 text-sm">
                  <span className="min-w-0 flex-1 truncate text-on-surface">{it.name}</span>
                  <span className="shrink-0 text-xs text-on-surface-variant">
                    {formatMoney(it.precio_unitario ?? 0, list.currency)} × {it.cantidad}
                  </span>
                  <span className="shrink-0 font-semibold text-on-surface">
                    {formatMoney(it.subtotal, list.currency)}
                  </span>
                </li>
              ))}
            </ul>
            <div className="flex items-end justify-between gap-2 border-t border-glass-border pt-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
                {t("checklists.receiptTotal")}
              </span>
              <div className="text-right">
                <p className="text-xl font-bold text-on-surface">
                  {formatMoney(bigTotal, list.currency, { symbol: true })}
                </p>
                <p className="text-xs text-on-surface-variant">
                  {list.currency === "USD"
                    ? `≈ ${formatMoney(convertedTotal.ves, "VES", { symbol: true })}`
                    : `≈ ${formatMoney(convertedTotal.usd, "USD", { symbol: true })}`}
                </p>
              </div>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor={`complete-account-${list.id}`}>{t("checklists.completeAccount")}</Label>
            <select
              id={`complete-account-${list.id}`}
              value={walletId}
              onChange={(e) => setWalletId(e.target.value)}
              required
              disabled={complete.isPending}
              className="h-11 w-full min-w-0 rounded-xl border border-glass-border bg-glass-surface px-3 py-2.5 text-base text-on-surface shadow-sm outline-none transition-colors backdrop-blur-md focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 md:text-sm"
            >
              <option value="" disabled>
                {t("checklists.completeAccountPlaceholder")}
              </option>
              {eligibleWallets.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name} · {formatMoney(w.saldo, w.currency, { symbol: true })}
                </option>
              ))}
            </select>
            {eligibleWallets.length === 0 && (
              <p className="rounded-lg bg-surface-container-high px-3 py-2 text-xs text-on-surface-variant">
                {t("wallets.noRegular")}
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor={`complete-total-${list.id}`}>{t("checklists.totalReal")}</Label>
            <Input
              id={`complete-total-${list.id}`}
              type="number"
              inputMode="decimal"
              step="0.01"
              min="0.01"
              value={total}
              onChange={(e) => setTotal(e.target.value)}
              placeholder="0.00"
              required
              aria-invalid={totalInvalid}
              aria-describedby={totalInvalid ? `complete-total-err-${list.id}` : undefined}
              disabled={complete.isPending}
            />
            <p className="text-xs text-on-surface-variant">{t("checklists.totalRealHint")}</p>
            {totalInvalid && (
              <p id={`complete-total-err-${list.id}`} className="text-xs text-status-delayed">
                {t("checklists.errorAmount")}
              </p>
            )}
          </div>

          {error && (
            <p className="rounded-lg bg-error-container/60 px-3 py-2 text-sm text-on-error-container">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              disabled={complete.isPending}
            >
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={complete.isPending || walletsLoading || !walletId || totalInvalid}>
              {complete.isPending ? t("checklists.completing") : t("checklists.complete")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ChecklistCard({
  list,
  rate,
}: {
  list: Checklist;
  rate: number | null;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [priceItem, setPriceItem] = useState<ChecklistItem | null>(null);
  const [completeOpen, setCompleteOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [newItemName, setNewItemName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const completed = list.estado === "completada";

  const patchItems = useMutation({
    mutationFn: (
      items: Array<Partial<ChecklistItem> & { name: string; is_checked: boolean; cantidad: number }>
    ) => api.patch<Checklist>(`/checklists/${list.id}`, { items }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.checklists });
      setError(null);
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) setError(err.message);
      else setError(t("errors.generic"));
    },
  });

  const remove = useMutation({
    mutationFn: () => api.delete(`/checklists/${list.id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.checklists });
      setConfirmOpen(false);
    },
  });

  function toggle(item: ChecklistItem) {
    if (completed) return;
    if (!item.is_checked && item.precio_unitario == null) {
      setPriceItem(item);
      return;
    }
    patchItems.mutate(
      list.items.map((x) =>
        x.id === item.id
          ? { id: x.id, name: x.name, precio_unitario: x.precio_unitario, cantidad: x.cantidad, is_checked: !x.is_checked }
          : x
      )
    );
  }

  function addItem(name: string) {
    setNewItemName("");
    patchItems.mutate([
      ...list.items.map((x) => ({
        id: x.id,
        name: x.name,
        precio_unitario: x.precio_unitario,
        cantidad: x.cantidad,
        is_checked: x.is_checked,
      })),
      { name, is_checked: false, cantidad: 1 },
    ]);
  }

  function removeItem(item: ChecklistItem) {
    if (completed) return;
    patchItems.mutate(
      list.items
        .filter((x) => x.id !== item.id)
        .map((x) => ({
          id: x.id,
          name: x.name,
          precio_unitario: x.precio_unitario,
          cantidad: x.cantidad,
          is_checked: x.is_checked,
        }))
    );
  }

  const checkedCount = list.items.filter((i) => i.is_checked).length;
  const pct = Number(list.progress_percent);
  const canComplete =
    list.items.length > 0 &&
    list.items.every(
      (i) =>
        i.is_checked &&
        i.precio_unitario != null &&
        Number(i.precio_unitario) > 0 &&
        Number(i.cantidad) >= 1
    );
  const converted = convertSubtotal(list.total_estimado, list.currency, rate);
  const convertedReal = completed
    ? convertSubtotal(list.total_real ?? "0", list.currency, rate)
    : null;

  return (
    <div className="glass-card clip-rounded-xl relative overflow-hidden rounded-xl bg-surface p-4">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10">
            <ShoppingBasket className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-on-surface">{list.name}</h3>
            <p className="text-xs text-on-surface-variant">{t("checklists.itemName")} · {list.currency}</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <Badge variant={ESTADO_BADGE[list.estado]}>
            {t(`checklists.${ESTADO_LABEL[list.estado]}`)}
          </Badge>
          {!completed && (
            <button
              type="button"
              aria-label={t("common.delete")}
              onClick={() => setConfirmOpen(true)}
              className="rounded-full p-1.5 text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-status-delayed"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Progreso */}
      <div className="mb-3">
        <div className="mb-1 flex items-end justify-between text-xs">
          <span className="text-on-surface-variant">
            {t("checklists.progress", {
              percent: pct.toFixed(0),
              checked: checkedCount,
              total: list.items.length,
            })}
          </span>
          <span className="font-semibold text-on-surface">{pct.toFixed(0)}%</span>
        </div>
        <div className="h-2.5 overflow-hidden rounded-full bg-surface-container-highest">
          <div
            className="h-full rounded-full bg-primary transition-all"
            style={{ width: `${Math.min(100, pct)}%` }}
          />
        </div>
      </div>

      {/* Productos */}
      <div className="space-y-1.5">
        {list.items.map((item) => {
          const itemConverted = convertSubtotal(item.precio_unitario ? item.subtotal : "0", list.currency, rate);
          return (
            <div
              key={item.id}
              className={cn(
                "flex items-center gap-3 rounded-xl border px-3 py-2",
                item.is_checked
                  ? "border-primary/20 bg-primary/5"
                  : "border-glass-border bg-glass-surface"
              )}
            >
              <button
                type="button"
                role="checkbox"
                aria-checked={item.is_checked}
                disabled={completed || patchItems.isPending}
                onClick={() => toggle(item)}
                className={cn(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-md border-2 transition-colors",
                  item.is_checked
                    ? "border-primary bg-primary text-on-primary"
                    : "border-on-surface-variant text-transparent"
                )}
              >
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={3}>
                  <path d="m5 12 5 5L20 7" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
              <div className="min-w-0 flex-1">
                <p
                  className={cn(
                    "truncate text-sm",
                    item.is_checked ? "text-on-surface line-through opacity-60" : "text-on-surface"
                  )}
                >
                  {item.name}
                </p>
                {item.precio_unitario != null && (
                  <p className="text-xs text-on-surface-variant">
                    {formatMoney(item.precio_unitario, list.currency)} × {item.cantidad}
                  </p>
                )}
              </div>
              <div className="text-right">
                {item.precio_unitario != null ? (
                  <>
                    <p className="text-sm font-semibold text-on-surface">
                      {formatMoney(item.subtotal, list.currency, { symbol: true })}
                    </p>
                    <p className="text-[11px] text-on-surface-variant">
                      {list.currency === "USD"
                        ? formatMoney(itemConverted.ves, "VES", { symbol: true })
                        : formatMoney(itemConverted.usd, "USD", { symbol: true })}
                    </p>
                  </>
                ) : (
                  <span className="text-[11px] font-medium text-on-surface-variant">
                    {t("checklists.statusEnCurso")}
                  </span>
                )}
              </div>
              {!completed && (
                <button
                  type="button"
                  aria-label={t("common.delete")}
                  disabled={patchItems.isPending}
                  onClick={() => removeItem(item)}
                  className="shrink-0 rounded-full p-1.5 text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-status-delayed"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </div>
          );
        })}

        {!completed && (
          <form
            className="flex items-center gap-2 rounded-xl border border-dashed border-outline px-3 py-2"
            onSubmit={(e) => {
              e.preventDefault();
              const name = newItemName.trim();
              if (name) addItem(name);
            }}
          >
            <Plus className="h-4 w-4 shrink-0 text-primary" />
            <input
              type="text"
              value={newItemName}
              onChange={(e) => setNewItemName(e.target.value)}
              placeholder={t("checklists.addItem")}
              maxLength={80}
              className="w-full bg-transparent text-sm text-on-surface outline-none placeholder:text-on-surface-variant"
            />
          </form>
        )}
      </div>

      {error && (
        <p className="mt-3 rounded-lg bg-error-container/60 px-3 py-2 text-sm text-on-error-container">
          {error}
        </p>
      )}

      {/* Pie: total y acción */}
      <div className="mt-4 space-y-3">
        <div
          className={cn(
            "flex items-end justify-between rounded-xl px-4 py-3",
            completed ? "bg-surface-container-low" : "bg-primary/10"
          )}
        >
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
              {completed ? t("checklists.totalPaid") : t("checklists.totalEstimated")}
            </p>
            <p className="text-xl font-bold text-on-surface">
              {list.currency === "USD"
                ? formatMoney(completed ? (convertedReal?.usd ?? 0) : converted.usd, "USD", { symbol: true })
                : formatMoney(completed ? (convertedReal?.ves ?? 0) : converted.ves, "VES", { symbol: true })}
            </p>
          </div>
          <div className="text-right text-xs text-on-surface-variant">
            {list.currency === "USD" ? (
              <span>
                ≈ {formatMoney(completed ? (convertedReal?.ves ?? 0) : converted.ves, "VES", { symbol: true })}
              </span>
            ) : (
              <span>
                ≈ {formatMoney(completed ? (convertedReal?.usd ?? 0) : converted.usd, "USD", { symbol: true })}
              </span>
            )}
            {completed && list.wallet_name && (
              <p className="mt-0.5">{t("checklists.fromAccount", { wallet: list.wallet_name })}</p>
            )}
            {completed && list.completed_at && (
              <p className="mt-0.5">
                {t("checklists.completedOn")} {new Date(list.completed_at).toLocaleDateString()}
              </p>
            )}
          </div>
        </div>

        {!completed && (
          <Button
            type="button"
            variant="glow"
            className="w-full"
            disabled={!canComplete}
            onClick={() => setCompleteOpen(true)}
          >
            {t("checklists.completeTitle")}
          </Button>
        )}
      </div>

      {priceItem !== null && (
        <PriceDialog
          list={list}
          item={priceItem}
          open
          onOpenChange={(open) => {
            if (!open) setPriceItem(null);
          }}
        />
      )}
      <CompleteDialog list={list} open={completeOpen} onOpenChange={setCompleteOpen} />
      <ConfirmDeleteDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        itemName={t("checklists.itemName")}
        itemLabel={list.name}
        pending={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
    </div>
  );
}

function useRate(): number | null {
  const { data: overview } = useOverview();
  return overview?.rate ? Number(overview.rate) : null;
}

function NewChecklistDialog() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState<Currency>("USD");
  const [error, setError] = useState<string | null>(null);

  const nameInvalid = name.trim() === "" || name.length > 120;

  const create = useMutation({
    mutationFn: () =>
      api.post<Checklist>("/checklists", {
        name: name.trim(),
        currency,
        items: [],
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.checklists });
      sileo.success({ title: t("checklists.created") });
      setOpen(false);
      setName("");
      setCurrency("USD");
      setError(null);
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) setError(err.message);
      else setError(t("errors.generic"));
    },
  });

  return (
    <>
      <Button variant="glow" onClick={() => setOpen(true)}>
        <Plus className="h-4 w-4" /> {t("checklists.newOne")}
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("checklists.newOne")}</DialogTitle>
            <DialogDescription>{t("checklists.subtitle")}</DialogDescription>
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
              <Label htmlFor="checklist-name">{t("checklists.name")}</Label>
              <Input
                id="checklist-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("checklists.namePlaceholder")}
                maxLength={120}
                required
                aria-invalid={nameInvalid}
                aria-describedby={nameInvalid ? "checklist-name-err" : undefined}
              />
              {nameInvalid && (
                <p id="checklist-name-err" className="text-xs text-status-delayed">
                  {t("checklists.errorName")}
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label>{t("wallet.currency")}</Label>
              <div className="flex gap-2">
                {(["USD", "VES"] as const).map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => setCurrency(c)}
                    className={cn(
                      "flex-1 rounded-xl border px-3 py-2.5 text-sm font-semibold transition-colors",
                      currency === c
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-glass-border bg-glass-surface text-on-surface-variant"
                    )}
                  >
                    {c}
                  </button>
                ))}
              </div>
            </div>

            {error && (
              <p className="rounded-lg bg-error-container/60 px-3 py-2 text-sm text-on-error-container">
                {error}
              </p>
            )}

            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setOpen(false)} disabled={create.isPending}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={create.isPending || nameInvalid}>
                {create.isPending ? t("common.loading") : t("common.save")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

export default function ChecklistsPage() {
  const { t } = useTranslation();
  const { data, isLoading, isError, refetch } = useChecklists();
  const rate = useRate();

  return (
    <div className="mt-4 space-y-6">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
            <ShoppingBasket size={20} className="text-primary" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-on-surface">{t("checklists.title")}</h2>
            <p className="text-sm text-on-surface-variant">{t("checklists.subtitle")}</p>
          </div>
        </div>
        <NewChecklistDialog />
      </div>

      {isError ? (
        <div className="glass-panel clip-rounded-lg rounded-lg p-6 text-center">
          <p className="mb-3 text-sm text-on-surface-variant">{t("errors.generic")}</p>
          <Button size="sm" variant="outline" onClick={() => refetch()}>
            {t("common.retry")}
          </Button>
        </div>
      ) : isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-52 w-full" />
          <Skeleton className="h-52 w-full" />
          <Skeleton className="h-52 w-full" />
        </div>
      ) : (data ?? []).length === 0 ? (
        <p className="glass-panel clip-rounded-lg rounded-lg p-6 text-center text-sm text-on-surface-variant">
          {t("checklists.empty")}
        </p>
      ) : (
        <div className="space-y-2">
          {(data ?? []).map((list) => (
            <ChecklistCard key={list.id} list={list} rate={rate} />
          ))}
        </div>
      )}
    </div>
  );
}