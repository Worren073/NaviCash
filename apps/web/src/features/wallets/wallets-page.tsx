import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { CreditCard, PiggyBank, Plus } from "lucide-react";
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
import { formatMoney } from "@/lib/format";
import { WALLET_COLORS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import type { Currency, Wallet } from "@/lib/types";

const SELECT_CLS =
  "h-11 w-full min-w-0 rounded-xl border border-glass-border bg-glass-surface backdrop-blur-md px-3 py-2.5 text-base text-on-surface shadow-sm outline-none transition-colors focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 md:text-sm";

export function NewWalletDialog({
  defaultTipo = "cash",
}: {
  defaultTipo?: Wallet["tipo"];
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
        className="glass-card cursor-pointer rounded-xl bg-surface p-4 transition-transform active:scale-[0.99]"
      >
        <div className="mb-4 flex items-start justify-between">
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
            <AdjustBalanceDialog wallet={wallet} />
          </div>
        </div>
        <div className="flex justify-between rounded-lg border border-outline-variant bg-surface-container-low p-3">
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
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

function AdjustBalanceDialog({ wallet }: { wallet: Wallet }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
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
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) setError(err.message);
      else setError(t("errors.generic"));
    },
  });

  return (
    <Dialog>
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
  const { data: overview } = useOverview();
  const { data: wallets, isLoading, isError } = useWallets();

  const usdValues = new Map<string, string>(
    (overview?.wallets ?? []).map((w) => [w.id, w.usd_value])
  );

  return (
    <div className="mt-4 space-y-8">
      <section>
        <h2 className="mb-1 text-3xl font-bold text-on-surface">{t("wallet.title")}</h2>
        <p className="text-base text-on-surface-variant">{t("wallet.subtitle")}</p>

        {/* Total Balance (Bento) */}
        <BlurLoading loading={isLoading}>
          <div className="glass-card relative mt-6 overflow-hidden rounded-xl bg-surface-container-low p-6">
          <div className="absolute -right-10 -top-10 h-32 w-32 rounded-full bg-primary/10 blur-3xl" />
          <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
            {t("wallet.totalUsd")}
          </p>
          <div className="flex items-end gap-2">
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

      {/* Wallets list */}
      <section className="space-y-2">
        {isError ? (
          <p className="glass-panel rounded-lg p-6 text-center text-sm text-on-surface-variant">
            {t("errors.generic")}
          </p>
        ) : isLoading ? (
          <>
            <Skeleton className="h-28 w-full" />
            <Skeleton className="h-28 w-full" />
          </>
        ) : (
          (wallets ?? []).map((wallet) => (
            <EditWalletDialog
              key={wallet.id}
              wallet={wallet}
              usdValue={usdValues.get(wallet.id) ?? wallet.saldo}
            />
          ))
        )}

        {/* Add wallet */}
        <NewWalletDialog />
      </section>
    </div>
  );
}