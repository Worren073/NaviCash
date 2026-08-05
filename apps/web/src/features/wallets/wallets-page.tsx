import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
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
import type { Wallet } from "@/lib/types";

function WalletIcon({ tipo }: { tipo: string }) {
  const cls = "h-5 w-5";
  if (tipo === "bank") return <CreditCard className={cls + " text-primary"} />;
  return <PiggyBank className={cls + " text-primary"} />;
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
            <div key={wallet.id} className="glass-card rounded-xl bg-surface p-4">
              <div className="mb-4 flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-full border border-primary/20 bg-primary/10">
                    <WalletIcon tipo={wallet.tipo} />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-on-surface">{wallet.name}</h3>
                    <p className="text-xs text-on-surface-variant">{wallet.currency}</p>
                  </div>
                </div>
                <AdjustBalanceDialog wallet={wallet} />
              </div>
              <div className="flex justify-between rounded-lg border border-outline-variant bg-surface-container-low p-3">
                <div>
                  <p className="mb-0.5 text-xs text-on-surface-variant">
                    {t("wallet.originalBalance")}
                  </p>
                  <p className="text-lg font-medium text-on-surface">
                    {formatMoney(wallet.saldo, wallet.currency, { symbol: true })}
                  </p>
                </div>
                <div className="text-right">
                  <p className="mb-0.5 text-xs text-on-surface-variant">{t("wallet.usdEquivalent")}</p>
                  <p className="text-lg font-medium text-on-surface">
                    {formatMoney(
                      usdValues.get(wallet.id) ?? wallet.saldo,
                      "USD",
                      { symbol: true }
                    )}
                  </p>
                </div>
              </div>
            </div>
          ))
        )}

        {/* Add wallet */}
        <button
          type="button"
          className="mt-4 flex w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-outline bg-surface-container-low py-4 transition-colors hover:bg-surface-container-high"
        >
          <Plus className="h-7 w-7 text-primary" />
          <span className="text-sm font-medium text-on-surface-variant">{t("wallet.addNew")}</span>
        </button>
      </section>
    </div>
  );
}