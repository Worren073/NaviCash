import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  ArrowLeftRight,
  ChevronRight,
  PersonStanding,
  Plus,
  Store,
  TrendingDown,
  TrendingUp,
  Wrench,
} from "lucide-react";

import { useBusinessSummary } from "@/hooks/use-queries";
import { useHideBalances } from "@/hooks/use-hide-balances";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { formatMoney, formatRelativeEvent } from "@/lib/format";
import { TrendSparkline } from "@/features/dashboard/trend-sparkline";
import type { Transaction } from "@/lib/types";

function TxIcon({ concepto }: { concepto: string }) {
  const map: Array<{ re: RegExp; Icon: typeof Store }> = [
    { re: /distrib|proveed|tienda|venta|cliente/i, Icon: Store },
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
    <div className="glass-panel clip-rounded-lg flex items-center justify-between rounded-lg p-4">
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
            {isTransfer ? t("wallet.transferRowLabel") : tx.concepto}
          </div>
          <div className="text-xs text-on-surface-variant">
            {formatRelativeEvent(tx.created_at)}
          </div>
        </div>
      </div>
      <div>
        <div className={`text-sm font-semibold ${isIncome ? "text-income-text" : "text-on-surface"}`}>
          {sign}
          {formatMoney(tx.monto, tx.moneda, { symbol: true })}
        </div>
        {!isTransfer && (
          <Badge variant="secondary" className="mt-1">
            {tx.estado === "pagado" ? t("common.pagado") : t("common.pendiente")}
          </Badge>
        )}
      </div>
    </div>
  );
}

export function BusinessDashboard() {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useBusinessSummary();
  const { hidden: hideBalances } = useHideBalances();

  return (
    <div className="space-y-8">
      <div className="pattern-noise glass-panel-elevated clip-rounded-4xl relative overflow-hidden rounded-[2rem] p-6">
        <div className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative z-10">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
              {t("business.dashboard.saldo")}
            </span>
            <Badge variant="secondary">{data?.currency}</Badge>
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            {isLoading ? (
              <Skeleton className="h-10 w-40" />
            ) : (
              <span className="text-4xl font-bold tracking-tight text-on-surface">
                {hideBalances
                  ? "••••"
                  : formatMoney(data?.saldo ?? 0, data?.currency, { symbol: true })}
              </span>
            )}
          </div>
        </div>
      </div>

      <section className="grid grid-cols-2 gap-2 md:gap-3">
        <div className="glass-panel clip-rounded-lg flex min-h-32 flex-col justify-between rounded-lg p-4 md:min-h-40">
          <div className="flex items-center justify-between gap-2">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-income/20">
              <TrendingUp className="h-4 w-4 text-income-text" />
            </div>
            <span className="text-xs font-semibold text-on-surface-variant">
              {t("business.dashboard.ingresos")}
            </span>
          </div>
          <div>
            {isLoading ? (
              <Skeleton className="h-7 w-24" />
            ) : (
              <>
                <div className="text-2xl font-semibold text-on-surface">
                  {hideBalances
                    ? "••••"
                    : formatMoney(data?.ingresos_mes ?? 0, data?.currency, { symbol: true })}
                </div>
                <div className="text-xs text-on-surface-variant">{t("business.dashboard.thisMonth")}</div>
              </>
            )}
          </div>
          <TrendSparkline trend="up" color="var(--color-income)" className="h-8 w-full" />
        </div>

        <div className="glass-panel clip-rounded-lg flex min-h-32 flex-col justify-between rounded-lg p-4 md:min-h-40">
          <div className="flex items-center justify-between gap-2">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-expense/20">
              <TrendingDown className="h-4 w-4 text-expense" />
            </div>
            <span className="text-xs font-semibold text-on-surface-variant">
              {t("business.dashboard.egresos")}
            </span>
          </div>
          <div>
            {isLoading ? (
              <Skeleton className="h-7 w-24" />
            ) : (
              <>
                <div className="text-2xl font-semibold text-on-surface">
                  {hideBalances
                    ? "••••"
                    : formatMoney(data?.egresos_mes ?? 0, data?.currency, { symbol: true })}
                </div>
                <div className="text-xs text-on-surface-variant">{t("business.dashboard.thisMonth")}</div>
              </>
            )}
          </div>
          <TrendSparkline trend="down" color="var(--color-expense)" className="h-8 w-full" />
        </div>
      </section>

      <div className="flex flex-col gap-2">
        <Link to="/operations/new" className="w-full md:w-64">
          <Button variant="glow" size="lg" className="w-full gap-2">
            <Plus className="h-5 w-5" />
            {t("business.dashboard.newOperation")}
          </Button>
        </Link>
      </div>

      <section>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-2xl font-semibold text-on-surface">{t("business.dashboard.recent")}</h2>
          <Link
            to="/transactions"
            className="text-sm text-primary transition-opacity hover:opacity-80"
          >
            {t("business.dashboard.viewAll")} <ChevronRight className="inline h-4 w-4" />
          </Link>
        </div>

        {isError ? (
          <p className="glass-panel clip-rounded-lg rounded-lg p-6 text-center text-sm text-on-surface-variant">
            {t("errors.generic")}
          </p>
        ) : isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : (data?.recent?.length ?? 0) === 0 ? (
          <div className="glass-panel clip-rounded-lg rounded-lg p-6 text-center text-sm text-on-surface-variant">
            {t("business.dashboard.noRecent")}
          </div>
        ) : (
          <div className="space-y-2">
            {(data?.recent ?? []).map((tx) => (
              <TxRow key={tx.id} tx={tx} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}