import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeftRight, CreditCard, PiggyBank, Plus, Trash2 } from "lucide-react";
import { sileo } from "sileo";
import { PenIcon } from "@/components/icons";

import { useOverview, useWallets, queryKeys } from "@/hooks/use-queries";
import { api, ApiErrorClass } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { BlurLoading } from "@/components/ui/blur-loading";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Segmented } from "@/components/ui/segmented";
import { formatMoney, formatSymbol } from "@/lib/format";
import { WALLET_COLORS } from "@/lib/constants";
import { CardGlow } from "@/components/ui/card-glow";
import { ConfirmDeleteDialog } from "@/components/ui/confirm-delete-dialog";
import { BalanceCard } from "@/features/dashboard/balance-card";
import { cn } from "@/lib/utils";
import type { Currency, Wallet } from "@/lib/types";

const SELECT_CLS =
  "h-11 w-full min-w-0 rounded-xl border border-glass-border bg-glass-surface backdrop-blur-md px-3 py-2.5 text-base text-on-surface shadow-sm outline-none transition-colors focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 md:text-sm";

export function NewWalletDialog({
  defaultTipo = "cash",
  lockTipo = false,
}: {
  defaultTipo?: Wallet["tipo"];
  /** Fija el tipo (p.ej. "saving") como solo lectura en el formulario. */
  lockTipo?: boolean;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState<Currency>("USD");
  const [tipo, setTipo] = useState<Wallet["tipo"]>(defaultTipo);
  const [color, setColor] = useState<string>("#006a61");
  const [saldoInicial, setSaldoInicial] = useState("0");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      api.post<Wallet>("/wallets", {
        name: name.trim(),
        currency,
        tipo,
        color,
        saldo_inicial: saldoInicial,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.wallets });
      void queryClient.invalidateQueries({ queryKey: queryKeys.overview });
      setOpen(false);
      setName("");
      setSaldoInicial("0");
      setColor("#006a61");
      setError(null);
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) setError(err.message);
      else setError(t("errors.generic"));
    },
  });

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-4 flex w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-outline bg-surface-container-low py-4 transition-colors hover:bg-surface-container-high"
      >
        <Plus className="h-7 w-7 text-primary" />
        <span className="text-sm font-medium text-on-surface-variant">{t("wallet.addNew")}</span>
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("wallet.newTitle")}</DialogTitle>
            <DialogDescription>{t("wallet.subtitle")}</DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setError(null);
              create.mutate();
            }}
            className="space-y-4"
          >
            <div className="space-y-1.5">
              <Label htmlFor="wallet-name">{t("wallet.name")}</Label>
              <Input
                id="wallet-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("wallet.namePlaceholder")}
                maxLength={80}
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="wallet-currency">{t("wallet.currency")}</Label>
                <select
                  id="wallet-currency"
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value as Currency)}
                  className={SELECT_CLS}
                >
                  <option value="USD">{t("wallet.currencyUsd")}</option>
                  <option value="VES">{t("wallet.currencyVes")}</option>
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="wallet-tipo">{t("wallet.type")}</Label>
                {lockTipo ? (
                  <div
                    id="wallet-tipo"
                    className="flex h-11 w-full items-center rounded-xl border border-glass-border bg-surface-container px-4 text-base text-on-surface-variant"
                  >
                    {t("wallet.typeSaving")}
                  </div>
                ) : (
                  <select
                    id="wallet-tipo"
                    value={tipo}
                    onChange={(e) => setTipo(e.target.value as Wallet["tipo"])}
                    className={SELECT_CLS}
                  >
                    <option value="cash">{t("wallet.typeCash")}</option>
                    <option value="bank">{t("wallet.typeBank")}</option>
                    <option value="saving">{t("wallet.typeSaving")}</option>
                    <option value="other">{t("wallet.typeOther")}</option>
                  </select>
                )}
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>{t("wallet.color")}</Label>
              <div className="flex flex-wrap gap-2">
                {WALLET_COLORS.map((c) => (
                  <button
                    key={c}
                    type="button"
                    aria-label={c}
                    onClick={() => setColor(c)}
                    className={cn(
                      "h-8 w-8 rounded-full border-2 transition-all",
                      color === c
                        ? "scale-110 border-on-surface"
                        : "border-transparent opacity-80 hover:opacity-100"
                    )}
                    style={{ backgroundColor: c }}
                  />
                ))}
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="wallet-initial">{t("wallet.initialBalance")}</Label>
              <Input
                id="wallet-initial"
                type="number"
                step="0.01"
                min="0"
                value={saldoInicial}
                onChange={(e) => setSaldoInicial(e.target.value)}
                required
              />
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
                onClick={() => setOpen(false)}
                disabled={create.isPending}
              >
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={create.isPending}>
                {create.isPending ? t("common.loading") : t("common.add")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

function WalletIcon({ tipo, color = "#006a61" }: { tipo: string; color?: string }) {
  const cls = "h-5 w-5";
  if (tipo === "bank") return <CreditCard className={cls} style={{ color }} />;
  return <PiggyBank className={cls} style={{ color }} />;
}

export function EditWalletDialog({ wallet, usdValue }: { wallet: Wallet; usdValue: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [name, setName] = useState(wallet.name);
  const [tipo, setTipo] = useState<Wallet["tipo"]>(wallet.tipo);
  const [color, setColor] = useState<string>(wallet.color || "#006a61");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName(wallet.name);
      setTipo(wallet.tipo);
      setColor(wallet.color || "#006a61");
      setError(null);
    }
  }, [open, wallet]);

  const update = useMutation({
    mutationFn: () =>
      api.patch<Wallet>(`/wallets/${wallet.id}`, {
        name: name.trim(),
        tipo,
        color,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.wallets });
      void queryClient.invalidateQueries({ queryKey: queryKeys.overview });
      setOpen(false);
      setError(null);
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) setError(err.message);
      else setError(t("errors.generic"));
    },
  });

  const remove = useMutation({
    mutationFn: () => api.delete(`/wallets/${wallet.id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.wallets });
      void queryClient.invalidateQueries({ queryKey: queryKeys.overview });
      void queryClient.invalidateQueries({ queryKey: queryKeys.savings });
      setOpen(false);
      setConfirmOpen(false);
    },
    onError: (err) => {
      sileo.error({
        title: t("errors.generic"),
        description:
          err instanceof ApiErrorClass ? err.message : undefined,
      });
    },
  });

  return (
    <>
      <div
        role="button"
        tabIndex={0}
        aria-label={t("wallet.editTitle")}
        onClick={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setOpen(true);
          }
        }}
        className="glass-card clip-rounded-xl relative cursor-pointer overflow-hidden rounded-xl bg-surface p-4 transition-transform active:scale-[0.99]"
      >
        <CardGlow color={wallet.color || "#006a61"} />
        <div className="relative mb-4 flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div
              className="flex h-10 w-10 items-center justify-center rounded-full border"
              style={{
                backgroundColor: `${wallet.color || "#006a61"}1a`,
                borderColor: `${wallet.color || "#006a61"}40`,
              }}
            >
              <WalletIcon tipo={wallet.tipo} color={wallet.color} />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-on-surface">{wallet.name}</h3>
              <p className="text-xs text-on-surface-variant">{wallet.currency}</p>
            </div>
          </div>
          <div onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-1.5">
              <AdjustBalanceDialog wallet={wallet} />
              <TransferWalletDialog defaultSource={wallet} />
            </div>
          </div>
        </div>
        <div className="relative flex justify-between rounded-lg border border-outline-variant bg-surface-container-low p-3">
          <div>
            <p className="mb-0.5 text-xs text-on-surface-variant">{t("wallet.originalBalance")}</p>
            <p className="text-lg font-medium text-on-surface">
              {formatMoney(wallet.saldo, wallet.currency, { symbol: true })}
            </p>
          </div>
          <div className="text-right">
            <p className="mb-0.5 text-xs text-on-surface-variant">{t("wallet.usdEquivalent")}</p>
            <p className="text-lg font-medium text-on-surface">
              {formatMoney(usdValue, "USD", { symbol: true })}
            </p>
          </div>
        </div>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("wallet.editTitle")}</DialogTitle>
            <DialogDescription>{wallet.name}</DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setError(null);
              update.mutate();
            }}
            className="space-y-4"
          >
            <div className="space-y-1.5">
              <Label htmlFor={`wallet-edit-name-${wallet.id}`}>{t("wallet.name")}</Label>
              <Input
                id={`wallet-edit-name-${wallet.id}`}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("wallet.namePlaceholder")}
                maxLength={80}
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>{t("wallet.currency")}</Label>
                <div className="flex h-11 w-full items-center rounded-xl border border-glass-border bg-surface-container px-4 text-base text-on-surface-variant">
                  {wallet.currency}
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor={`wallet-edit-tipo-${wallet.id}`}>{t("wallet.type")}</Label>
                <select
                  id={`wallet-edit-tipo-${wallet.id}`}
                  value={tipo}
                  onChange={(e) => setTipo(e.target.value as Wallet["tipo"])}
                  className={SELECT_CLS}
                >
                  <option value="cash">{t("wallet.typeCash")}</option>
                  <option value="bank">{t("wallet.typeBank")}</option>
                  <option value="saving">{t("wallet.typeSaving")}</option>
                  <option value="other">{t("wallet.typeOther")}</option>
                </select>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>{t("wallet.color")}</Label>
              <div className="flex flex-wrap gap-2">
                {WALLET_COLORS.map((c) => (
                  <button
                    key={c}
                    type="button"
                    aria-label={c}
                    onClick={() => setColor(c)}
                    className={cn(
                      "h-8 w-8 rounded-full border-2 transition-all",
                      color === c
                        ? "scale-110 border-on-surface"
                        : "border-transparent opacity-80 hover:opacity-100"
                    )}
                    style={{ backgroundColor: c }}
                  />
                ))}
              </div>
            </div>

            {error && (
              <p className="rounded-lg bg-error-container/60 px-3 py-2 text-sm text-on-error-container">
                {error}
              </p>
            )}

            <DialogFooter>
              <div className="flex w-full items-center justify-between gap-2">
                <Button
                  type="button"
                  variant="destructive"
                  onClick={() => setConfirmOpen(true)}
                  disabled={update.isPending}
                >
                  <Trash2 className="h-4 w-4" /> {t("common.delete")}
                </Button>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => setOpen(false)}
                    disabled={update.isPending}
                  >
                    {t("common.cancel")}
                  </Button>
                  <Button type="submit" disabled={update.isPending}>
                    {update.isPending ? t("common.loading") : t("common.save")}
                  </Button>
                </div>
              </div>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDeleteDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        itemName={t("wallet.item")}
        itemLabel={wallet.name}
        pending={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
    </>
  );
}

export function TransferWalletDialog({
  defaultSource,
  open,
  onOpenChange,
}: {
  defaultSource?: Wallet;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: wallets } = useWallets();
  const [internalOpen, setInternalOpen] = useState(false);
  const [sourceId, setSourceId] = useState(defaultSource?.id ?? "");
  const [targetId, setTargetId] = useState("");
  const [monto, setMonto] = useState("");
  const [rateSource, setRateSource] = useState<"oficial" | "manual">("oficial");
  const [customRate, setCustomRate] = useState("");
  const [error, setError] = useState<string | null>(null);

  const isControlled = open !== undefined;
  const dialogOpen = isControlled ? open : internalOpen;
  const setDialogOpen = (v: boolean) => {
    if (isControlled) onOpenChange?.(v);
    else setInternalOpen(v);
  };

  useEffect(() => {
    if (dialogOpen) {
      setSourceId(defaultSource?.id ?? "");
      setTargetId("");
      setMonto("");
      setRateSource("oficial");
      setCustomRate("");
      setError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dialogOpen]);

  const { data: rateData } = useQuery({
    queryKey: queryKeys.rates,
    queryFn: () => api.get<{ rate: string }>("/rates/current"),
    retry: false,
    staleTime: 5 * 60 * 1000,
    enabled: dialogOpen,
  });
  const officialRate = rateData?.rate ? Number(rateData.rate) : null;

  const source = (wallets ?? []).find((w) => w.id === sourceId);
  const target = (wallets ?? []).find((w) => w.id === targetId);
  const crossCurrency = !!source && !!target && source.currency !== target.currency;
  const isBuy = crossCurrency && source.currency === "VES"; // VES→USD: compra

  const rate =
    crossCurrency && rateSource === "manual" ? Number(customRate) : officialRate;

  const preview = useMemo(() => {
    if (!source || !target || !monto || Number(monto) <= 0) return null;
    const amount = Number(monto);
    if (!crossCurrency) return { amount, currency: source.currency };
    if (!rate || rate <= 0) return null;
    return isBuy
      ? { amount: amount / rate, currency: target.currency }
      : { amount: amount * rate, currency: target.currency };
  }, [source, target, monto, crossCurrency, rate, isBuy]);

  const transfer = useMutation({
    mutationFn: () =>
      api.post<{ detail: string }>("/wallets/transfer", {
        source: sourceId,
        target: targetId,
        amount: monto,
        rate_source: rateSource,
        custom_rate: rateSource === "manual" ? customRate : undefined,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.wallets });
      void queryClient.invalidateQueries({ queryKey: queryKeys.overview });
      void queryClient.invalidateQueries({ queryKey: queryKeys.transactions });
      setDialogOpen(false);
      setError(null);
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) setError(err.message);
      else setError(t("errors.generic"));
    },
  });

  const canSubmit =
    !!source && !!target && source.id !== target.id && !!monto && Number(monto) > 0 && (!crossCurrency || (rate && rate > 0));

  return (
    <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
      <DialogTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-1 rounded-lg border border-glass-border bg-glass-surface px-3 py-1.5 text-xs text-on-surface-variant backdrop-blur-md transition-all hover:bg-surface-container-high active:scale-95"
        >
          <ArrowLeftRight size={16} />
          {t("wallet.transfer")}
        </button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("wallet.transferTitle")}</DialogTitle>
          <DialogDescription>{t("wallet.transferSubtitle")}</DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            if (sourceId === targetId) {
              setError(t("wallet.transferSameWallet"));
              return;
            }
            transfer.mutate();
          }}
          className="space-y-4"
        >
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>{t("wallet.transferFrom")}</Label>
              <select
                value={sourceId}
                onChange={(e) => setSourceId(e.target.value)}
                className={SELECT_CLS}
              >
                <option value="">{t("wallet.transferFrom")}</option>
                {(wallets ?? []).map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name} · {formatMoney(w.saldo, w.currency)}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label>{t("wallet.transferTo")}</Label>
              <select
                value={targetId}
                onChange={(e) => setTargetId(e.target.value)}
                className={SELECT_CLS}
              >
                <option value="">{t("wallet.transferTo")}</option>
                {(wallets ?? []).map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name} · {formatMoney(w.saldo, w.currency)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>{t("wallet.transferAmount")}</Label>
            <div className="flex items-center gap-2">
              <span className="text-lg font-semibold text-on-surface">
                {source ? formatSymbol(source.currency) : ""}
              </span>
              <Input
                type="number"
                inputMode="decimal"
                step="0.01"
                min="0"
                value={monto}
                onChange={(e) => setMonto(e.target.value)}
                placeholder="0.00"
                required
              />
            </div>
          </div>

          {crossCurrency && (
            <>
              <div className="space-y-1.5">
                <Label>{t("wallet.transferRateLabel")}</Label>
                <div className="max-w-[280px]">
                  <Segmented
                    layoutId="seg-transfer-rate"
                    options={[
                      { value: "oficial", label: t("wallet.transferRateBcv") },
                      { value: "manual", label: t("wallet.transferRateCustom") },
                    ]}
                    value={rateSource}
                    onChange={setRateSource}
                  />
                </div>
              </div>

              {rateSource === "manual" && (
                <div className="space-y-1.5">
                  <Label>{t("wallet.transferCustomPlaceholder")}</Label>
                  <Input
                    type="number"
                    inputMode="decimal"
                    step="0.01"
                    min="0"
                    value={customRate}
                    onChange={(e) => setCustomRate(e.target.value)}
                    placeholder={t("wallet.transferCustomPlaceholder")}
                    required
                  />
                </div>
              )}

              <p className="rounded-lg border border-glass-border bg-surface-container-low px-3 py-2 text-sm text-on-surface-variant">
                {isBuy
                  ? t("wallet.transferCompra", { to: target.currency, from: source.currency })
                  : t("wallet.transferVenta", { from: source.currency, to: target.currency })}
              </p>

              {preview && (
                <p className="rounded-lg border border-primary/20 bg-primary/10 px-3 py-2 text-sm font-medium text-primary">
                  {t("wallet.transferPreview")}: {formatMoney(preview.amount, preview.currency, { symbol: true })}
                </p>
              )}
            </>
          )}

          {error && (
            <p className="rounded-lg bg-error-container/60 px-3 py-2 text-sm text-on-error-container">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setDialogOpen(false)}
              disabled={transfer.isPending}
            >
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={transfer.isPending || !canSubmit}>
              <ArrowLeftRight className="h-4 w-4" />
              {transfer.isPending ? t("common.loading") : t("wallet.transferBtn")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function AdjustBalanceDialog({ wallet }: { wallet: Wallet }) {  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [saldo, setSaldo] = useState(wallet.saldo);
  const [error, setError] = useState<string | null>(null);

  const adjust = useMutation({
    mutationFn: () =>
      api.post<{ detail: string }>(`/wallets/${wallet.id}/adjust`, {
        new_balance: saldo,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.wallets });
      void queryClient.invalidateQueries({ queryKey: queryKeys.overview });
      setOpen(false);
      setError(null);
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) setError(err.message);
      else setError(t("errors.generic"));
    },
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-1 rounded-lg border border-glass-border bg-glass-surface px-3 py-1.5 text-xs text-on-surface-variant backdrop-blur-md transition-all hover:bg-surface-container-high active:scale-95"
        >
          <PenIcon size={16} />
          {t("wallet.adjust")}
        </button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{wallet.name}</DialogTitle>
          <DialogDescription>{t("wallet.adjust")}</DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            adjust.mutate();
          }}
          className="space-y-4"
        >
          <div className="space-y-1.5">
            <Label htmlFor={`saldo-${wallet.id}`}>{t("wallet.initialBalance")}</Label>
            <Input
              id={`saldo-${wallet.id}`}
              type="number"
              step="0.01"
              value={saldo}
              onChange={(e) => setSaldo(e.target.value)}
              required
            />
          </div>
          {error && (
            <p className="rounded-lg bg-error-container/60 px-3 py-2 text-sm text-on-error-container">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button type="submit" disabled={adjust.isPending}>
              {adjust.isPending ? t("common.loading") : t("common.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function WalletsPage() {
  const { t } = useTranslation();
  const { data: overview, isLoading: overviewLoading } = useOverview();
  const { data: wallets, isLoading, isError } = useWallets();

  const usdValues = new Map<string, string>(
    (overview?.wallets ?? []).map((w) => [w.id, w.usd_value])
  );

  const savingWallets = (wallets ?? []).filter((w) => w.tipo === "saving");
  const regularWallets = (wallets ?? []).filter((w) => w.tipo !== "saving");
  const vesWallets = regularWallets.filter((w) => w.currency === "VES");
  const usdWallets = regularWallets.filter((w) => w.currency === "USD");

  const rate = overview?.rate ? Number(overview.rate) : null;
  const totalUsd = regularWallets.reduce(
    (acc, w) => acc + Number(usdValues.get(w.id) ?? 0),
    0
  );
  const totalVes = rate != null ? totalUsd * rate : null;
  const vesVes = vesWallets.reduce((acc, w) => acc + Number(w.saldo), 0);
  const vesUsd =
    rate != null
      ? vesWallets.reduce((acc, w) => acc + Number(usdValues.get(w.id) ?? 0), 0)
      : null;
  const usdUsd = usdWallets.reduce((acc, w) => acc + Number(w.saldo), 0);
  const usdVes = rate != null ? usdUsd * rate : null;

  const renderWallet = (wallet: Wallet) => (
    <EditWalletDialog
      key={wallet.id}
      wallet={wallet}
      usdValue={usdValues.get(wallet.id) ?? wallet.saldo}
    />
  );

  return (
    <div className="mt-4 space-y-8">
      <section>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="mb-1 text-3xl font-bold text-on-surface">{t("wallet.title")}</h2>
            <p className="text-base text-on-surface-variant">{t("wallet.subtitle")}</p>
          </div>
          <TransferWalletDialog />
        </div>

        {/* Balance Header (carrusel) */}
        <div className="mt-6 flex gap-3 overflow-x-auto pb-1 snap-x snap-mandatory scrollbar-hide">
          <BalanceCard
            label={t("dashboard.totalBalance")}
            symbol="$"
            amount={overviewLoading ? null : formatMoney(totalUsd, "USD")}
            isLoading={overviewLoading}
            equivalentLabel={t("dashboard.totalBs")}
            equivalentValue={
              overviewLoading || totalVes == null
                ? null
                : formatMoney(totalVes, "VES", { symbol: true })
            }
            showRate
            rate={overview?.rate ?? null}
          />
          <BalanceCard
            label={t("dashboard.vesBalance")}
            symbol="Bs"
            amount={overviewLoading ? null : formatMoney(vesVes, "VES")}
            isLoading={overviewLoading}
            equivalentLabel={t("dashboard.usdEquivalent")}
            equivalentValue={
              overviewLoading || vesUsd == null
                ? null
                : formatMoney(vesUsd, "USD", { symbol: true })
            }
            tone="flag"
          />
          <BalanceCard
            label={t("dashboard.usdBalance")}
            symbol="$"
            amount={overviewLoading ? null : formatMoney(usdUsd, "USD")}
            isLoading={overviewLoading}
            equivalentLabel={t("dashboard.totalBs")}
            equivalentValue={
              overviewLoading || usdVes == null
                ? null
                : formatMoney(usdVes, "VES", { symbol: true })
            }
            tone="green"
          />
        </div>

        {/* Total Balance (Bento) */}
        <BlurLoading loading={isLoading}>
          <div className="glass-card clip-rounded-xl relative mt-6 overflow-hidden rounded-xl bg-surface-container-low p-6">
          <CardGlow color="#006a61" />
          <p className="relative mb-1 text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
            {t("wallet.totalUsd")}
          </p>
          <div className="relative flex items-end gap-2">
            {isLoading ? (
              <Skeleton className="h-10 w-40" />
            ) : (
              <span className="text-4xl font-bold tracking-tight text-on-surface">
                {formatMoney(overview?.total_balance_usd ?? 0, "USD", { symbol: true })}
              </span>
            )}
          </div>
          </div>
        </BlurLoading>
      </section>

      {isError ? (
        <p className="glass-panel clip-rounded-lg rounded-lg p-6 text-center text-sm text-on-surface-variant">
          {t("errors.generic")}
        </p>
      ) : (
        <>
          {/* Cuentas normales */}
          <section className="space-y-2">
            <h3 className="text-lg font-semibold text-on-surface">{t("wallet.regularTitle")}</h3>
            {isLoading ? (
              <>
                <Skeleton className="h-28 w-full" />
                <Skeleton className="h-28 w-full" />
              </>
            ) : regularWallets.length === 0 ? (
              <p className="glass-panel clip-rounded-lg rounded-lg p-6 text-center text-sm text-on-surface-variant">
                {t("wallet.noRegular")}
              </p>
            ) : (
              <>
                {vesWallets.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="mt-2 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-on-surface-variant">
                      <span className="h-px flex-1 bg-glass-border" />
                      {t("wallet.vesAccounts")}
                      <span className="h-px flex-1 bg-glass-border" />
                    </h4>
                    {vesWallets.map(renderWallet)}
                  </div>
                )}
                {usdWallets.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="mt-2 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-on-surface-variant">
                      <span className="h-px flex-1 bg-glass-border" />
                      {t("wallet.usdAccounts")}
                      <span className="h-px flex-1 bg-glass-border" />
                    </h4>
                    {usdWallets.map(renderWallet)}
                  </div>
                )}
              </>
            )}
            <NewWalletDialog />
          </section>

          {/* Billeteras de ahorro */}
          <section className="space-y-2">
            <h3 className="text-lg font-semibold text-on-surface">{t("wallet.savingsTitle")}</h3>
            {isLoading ? (
              <>
                <Skeleton className="h-28 w-full" />
                <Skeleton className="h-28 w-full" />
              </>
            ) : savingWallets.length === 0 ? (
              <p className="glass-panel clip-rounded-lg rounded-lg p-6 text-center text-sm text-on-surface-variant">
                {t("wallet.noSaving")}
              </p>
            ) : (
              savingWallets.map(renderWallet)
            )}
            <NewWalletDialog defaultTipo="saving" lockTipo />
          </section>
        </>
      )}
    </div>
  );
}