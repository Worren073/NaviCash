import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  ArrowDown,
  ArrowLeftRight,
  ArrowUp,
  CalendarRange,
  ChevronRight,
  PersonStanding,
  PiggyBank,
  Store,
  TriangleAlert,
  Wrench,
} from "lucide-react";

import { useOverview, useWallets } from "@/hooks/use-queries";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { BlurLoading } from "@/components/ui/blur-loading";
import { NaviAvatar } from "@/features/assistant/navi-avatar";
import { useVoiceChat } from "@/features/assistant/voice-chat-context";
import { BalanceCard } from "@/features/dashboard/balance-card";
import { formatCompact, formatMoney, formatRelativeEvent } from "@/lib/format";
import type { Transaction } from "@/lib/types";

const STATE_BADGE: Record<string, "success" | "pending" | "delayed"> = {
  pagado: "success",
  pendiente: "pending",
  retrasado: "delayed",
};

function TxIcon({ concepto }: { concepto: string }) {
  const map: Array<{ re: RegExp; Icon: typeof Store }> = [
    { re: /distrib|proveed|tienda|mercado/i, Icon: Store },
    { re: /servicio|técnic|tecnic/i, Icon: Wrench },
    { re: /carlos|mar[ií]a|pedro|ana|jos[eé]|luis/i, Icon: PersonStanding },
  ];
  const hit = map.find(({ re }) => re.test(concepto));
  const Icon = hit?.Icon ?? Store;
  return (
    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-surface-container-high text-on-surface-variant">
      <Icon className="h-5 w-5" />
    </div>
  );
}

function TxRow({ tx }: { tx: Transaction }) {
  const { t } = useTranslation();
  const isIncome = tx.tipo === "cobro";
  const isTransfer = tx.tipo === "transferencia";
  const sign = isTransfer || isIncome ? "" : "-";
  return (
    <div className="glass-panel flex items-center justify-between clip-rounded-lg rounded-lg p-4">
      <div className="flex items-center gap-3">
        {isTransfer ? (
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-cyan-500/15 text-cyan-500">
            <ArrowLeftRight className="h-5 w-5" />
          </div>
        ) : (
          <TxIcon concepto={tx.concepto} />
        )}
        <div>
          <div className="text-sm font-medium text-on-surface">
            {isTransfer
              ? t("wallet.transferRowLabel")
              : `${tx.concepto}${tx.wallet_name ? ` · ${tx.wallet_name}` : ""}`}
          </div>
          <div className="text-xs text-on-surface-variant">
            {isTransfer
              ? `${tx.wallet_name ?? ""} → ${tx.dest_wallet_name ?? ""}`
              : formatRelativeEvent(tx.created_at)}
          </div>
        </div>
      </div>
      <div className="text-right">
        <div className={`text-sm font-semibold ${isIncome ? "text-income-text" : "text-on-surface"}`}>
          {sign}
          {formatMoney(tx.monto, tx.moneda, { symbol: true })}
        </div>
        {isTransfer ? (
          tx.moneda_destino && tx.moneda_destino !== tx.moneda ? (
            <div className="mt-1 text-xs font-medium text-on-surface-variant">
              {formatMoney(tx.monto_destino, tx.moneda_destino, { symbol: true })}
            </div>
          ) : null
        ) : (
          <Badge variant={STATE_BADGE[tx.estado]} className="mt-1">
            {t(`common.${tx.estado}`)}
          </Badge>
        )}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { t } = useTranslation();
  const { openVoice } = useVoiceChat();
  const { data, isLoading, isError, refetch } = useOverview();
  const { data: wallets } = useWallets();

  const usdValues = new Map<string, string>(
    (data?.wallets ?? []).map((w) => [w.id, w.usd_value])
  );
  const walletTipo = new Map((wallets ?? []).map((w) => [w.id, w.tipo]));
  const regularWallets = (data?.wallets ?? []).filter(
    (w) => walletTipo.get(w.id) !== "saving"
  );
  const vesWallets = regularWallets.filter((w) => w.currency === "VES");
  const usdWallets = regularWallets.filter((w) => w.currency === "USD");

  const savingsUsd = (wallets ?? [])
    .filter((w) => w.tipo === "saving")
    .reduce((acc, w) => acc + Number(usdValues.get(w.id) ?? w.saldo), 0);

  const rate = data?.rate ? Number(data.rate) : null;
  const totalUsd = regularWallets.reduce(
    (acc, w) => acc + Number(w.usd_value ?? 0),
    0
  );
  const totalVes = rate != null ? totalUsd * rate : null;
  const vesVes = vesWallets.reduce((acc, w) => acc + Number(w.saldo), 0);
  const vesUsd =
    rate != null
      ? vesWallets.reduce((acc, w) => acc + Number(w.usd_value ?? 0), 0)
      : null;
  const usdUsd = usdWallets.reduce((acc, w) => acc + Number(w.saldo), 0);
  const usdVes = rate != null ? usdUsd * rate : null;

  return (
    <div className="space-y-8">
      {/* Balance Header (carrusel) */}
      <div className="mt-4 flex gap-3 overflow-x-auto pb-1 snap-x snap-mandatory scrollbar-hide">
        <BalanceCard
          label={t("dashboard.totalBalance")}
          symbol="$"
          amount={isLoading ? null : formatMoney(totalUsd, "USD")}
          isLoading={isLoading}
          equivalentLabel={t("dashboard.totalBs")}
          equivalentValue={
            isLoading || totalVes == null
              ? null
              : formatMoney(totalVes, "VES", { symbol: true })
          }
          showRate
          rate={data?.rate ?? null}
        />
        <BalanceCard
          label={t("dashboard.vesBalance")}
          symbol="Bs"
          amount={isLoading ? null : formatMoney(vesVes, "VES")}
          isLoading={isLoading}
          equivalentLabel={t("dashboard.usdEquivalent")}
          equivalentValue={
            isLoading || vesUsd == null
              ? null
              : formatMoney(vesUsd, "USD", { symbol: true })
          }
          tone="flag"
        />
        <BalanceCard
          label={t("dashboard.usdBalance")}
          symbol="$"
          amount={isLoading ? null : formatMoney(usdUsd, "USD")}
          isLoading={isLoading}
          equivalentLabel={t("dashboard.totalBs")}
          equivalentValue={
            isLoading || usdVes == null
              ? null
              : formatMoney(usdVes, "VES", { symbol: true })
          }
          tone="green"
        />
      </div>

      {/* Accesos rápidos */}
      <div className="grid grid-cols-2 gap-2">
        <Link
          to="/savings"
          className="glass-panel clip-rounded-lg flex items-center justify-center gap-2 rounded-lg p-3 transition-transform hover:scale-[1.01] active:scale-[0.99]"
        >
          <PiggyBank className="h-5 w-5 text-emerald-500" />
          <span className="text-sm font-semibold text-on-surface">
            {t("menu.savings")}
          </span>
        </Link>
        <Link
          to="/subscriptions"
          className="glass-panel clip-rounded-lg flex items-center justify-center gap-2 rounded-lg p-3 transition-transform hover:scale-[1.01] active:scale-[0.99]"
        >
          <CalendarRange className="h-5 w-5 text-primary" />
          <span className="text-sm font-semibold text-on-surface">
            {t("menu.subscriptions")}
          </span>
        </Link>
        <button
          type="button"
          onClick={openVoice}
          aria-label={t("assistant.voice.title")}
          className="glass-panel clip-rounded-lg col-span-2 flex items-center justify-center gap-2 rounded-lg p-3 transition-transform hover:scale-[1.01] active:scale-[0.99]"
        >
          <NaviAvatar size={28} static className="shrink-0" />
          <span className="text-sm font-semibold text-on-surface">
            {t("assistant.voice.title")}
          </span>
        </button>
      </div>

      {/* Total en Ahorros (compacto) */}
      <Link to="/savings" className="block">
        <section className="glass-panel clip-rounded-xl relative overflow-hidden rounded-xl border border-glass-border px-5 py-4 transition-transform hover:scale-[1.01] active:scale-[0.99]">
          <div className="pointer-events-none absolute right-0 top-0 h-full w-24 bg-gradient-to-l from-primary/10 to-transparent" />
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
              {t("dashboard.totalSavings")}
            </span>
            <Badge variant="secondary">{t("savings.title")}</Badge>
          </div>
          <div className="mt-1">
            {isLoading ? (
              <Skeleton className="h-7 w-32" />
            ) : (
              <span className="text-2xl font-bold tracking-tight text-on-surface">
                {formatMoney(savingsUsd, "USD", { symbol: true })}
              </span>
            )}
          </div>
        </section>
      </Link>

      {/* Quick Stats Bento */}
      <BlurLoading loading={isLoading}>
        <section className="grid grid-cols-2 gap-2">
        <Link
          to="/transactions?tipo=cobro&estado=pendiente"
          className="glass-panel clip-rounded-lg flex aspect-[4/3] flex-col justify-between rounded-lg p-4 transition-transform hover:scale-[1.01] active:scale-[0.99]"
        >
          <div className="flex items-start justify-between">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-income/20">
              <ArrowDown className="h-4 w-4 text-income-text" />
            </div>
            <span className="rounded-full bg-income/10 px-2 py-0.5 text-xs font-semibold text-income-text">
              {t("common.toCollect")}
            </span>
          </div>
          <div>
            {isLoading ? (
              <Skeleton className="h-7 w-24" />
            ) : (
              <div className="text-2xl font-semibold text-on-surface">
                {formatCompact(Number(data?.to_receive ?? 0), "USD")}
              </div>
            )}
            <div className="text-xs text-on-surface-variant">
              {t("dashboard.incoming", {
                count: (data?.upcoming ?? []).filter((tx) => tx.tipo === "cobro").length,
              })}
            </div>
          </div>
        </Link>

        <Link
          to="/transactions?tipo=pago&estado=pendiente"
          className="glass-panel clip-rounded-lg flex aspect-[4/3] flex-col justify-between rounded-lg p-4 transition-transform hover:scale-[1.01] active:scale-[0.99]"
        >
          <div className="flex items-start justify-between">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-expense/20">
              <ArrowUp className="h-4 w-4 text-expense" />
            </div>
            <span className="rounded-full bg-expense/10 px-2 py-0.5 text-xs font-semibold text-expense">
              {t("common.toPay")}
            </span>
          </div>
          <div>
            {isLoading ? (
              <Skeleton className="h-7 w-24" />
            ) : (
              <div className="text-2xl font-semibold text-on-surface">
                {formatCompact(Number(data?.to_pay ?? 0), "USD")}
              </div>
            )}
            <div className="text-xs text-on-surface-variant">
              {t("dashboard.outgoing", {
                count: (data?.upcoming ?? []).filter((tx) => tx.tipo === "pago").length,
              })}
            </div>
          </div>
        </Link>
        </section>
      </BlurLoading>

      <Link
        to="/transactions?estado=retrasado"
        className="glass-panel clip-rounded-lg flex flex-1 items-center justify-between rounded-lg border-error/30 p-3 transition-transform hover:scale-[1.01] active:scale-[0.99]"
      >
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-full bg-status-delayed/20">
            <TriangleAlert className="h-3.5 w-3.5 text-delayed-text" />
          </div>
          <span className="text-sm text-delayed-text">{t("common.delayed")}</span>
        </div>
        {isLoading ? (
          <Skeleton className="h-5 w-14" />
        ) : (
          <span className="text-sm font-semibold text-on-surface">
            {formatCompact(Number(data?.overdue ?? 0), "USD")}
          </span>
        )}
      </Link>

      {/* Upcoming / Próximos vencimientos */}
      <section>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-2xl font-semibold text-on-surface">
            {t("dashboard.recentActivity")}
          </h2>
          <Link
            to="/transactions"
            className="text-sm text-primary transition-opacity hover:opacity-80"
          >
            {t("common.viewAll")} <ChevronRight className="inline h-4 w-4" />
          </Link>
        </div>

        {isError ? (
          <div className="glass-panel clip-rounded-lg rounded-lg p-6 text-center">
            <p className="mb-3 text-sm text-on-surface-variant">⚠️ {t("errors.generic")}</p>
            <Button size="sm" variant="outline" onClick={() => refetch()}>
              {t("common.retry")}
            </Button>
          </div>
        ) : isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : (
          <div className="space-y-2">
            {(data?.recent ?? []).map((tx) => <TxRow key={tx.id} tx={tx} />)}
            {(data?.recent ?? []).length === 0 && (
              <div className="glass-panel clip-rounded-lg rounded-lg p-6 text-center text-sm text-on-surface-variant">
                {t("dashboard.noRecent")}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}