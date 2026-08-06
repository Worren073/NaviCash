import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  ArrowDown,
  ArrowUp,
  ChevronRight,
  PersonStanding,
  Store,
  TriangleAlert,
  Wrench,
} from "lucide-react";

import { useOverview } from "@/hooks/use-queries";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { BlurLoading } from "@/components/ui/blur-loading";
import { CurrencyDollarIcon } from "@/components/icons";
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
  const sign = isIncome ? "+" : "-";
  return (
    <div className="glass-panel flex items-center justify-between rounded-lg p-4">
      <div className="flex items-center gap-3">
        <TxIcon concepto={tx.concepto} />
        <div>
          <div className="text-sm font-medium text-on-surface">{tx.concepto}</div>
          <div className="text-xs text-on-surface-variant">
            {formatRelativeEvent(tx.created_at)}
          </div>
        </div>
      </div>
      <div className="text-right">
        <div className={`text-sm font-semibold ${isIncome ? "text-income" : "text-on-surface"}`}>
          {sign}
          {formatMoney(tx.monto, tx.moneda, { symbol: true })}
        </div>
        <Badge variant={STATE_BADGE[tx.estado]} className="mt-1">
          {t(`common.${tx.estado}`)}
        </Badge>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { t } = useTranslation();
  const { data, isLoading, isError, refetch } = useOverview();

  return (
    <div className="space-y-8">
      {/* Balance Header */}
      <section className="glass-panel relative mt-4 overflow-hidden rounded-xl p-6">
        <div className="absolute inset-0 bg-gradient-to-br from-primary/10 to-transparent opacity-50" />
        <BlurLoading loading={isLoading}>
          <div className="relative z-10 flex flex-col items-center space-y-2 text-center">
            <span className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
              {t("dashboard.totalBalance")}
            </span>
            {isLoading ? (
              <Skeleton className="h-11 w-44" />
            ) : (
              <div className="flex items-baseline gap-1">
                <span className="text-2xl font-semibold text-primary">$</span>
                <span className="text-4xl font-bold tracking-tight text-on-surface">
                  {data?.total_balance_usd ?? "0.00"}
                </span>
              </div>
            )}
            {data?.total_balance_ves != null && (
              <div className="glass-panel mt-2 flex items-center gap-2 rounded-full px-4 py-1.5">
                <span className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
                  {t("dashboard.totalBs")}
                </span>
                <span className="text-sm font-bold text-on-surface">
                  {formatMoney(data.total_balance_ves, "VES", { symbol: true })}
                </span>
              </div>
            )}
            {data?.rate && (
              <>
                <div className="my-0.5 h-px w-24 bg-glass-border" />
                <div className="glass-panel flex items-center gap-2 rounded-full px-4 py-1.5">
                  <CurrencyDollarIcon size={16} className="text-primary" />
                  <span className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
                    {t("dashboard.bcvRate", {
                      rate: Number(data.rate).toFixed(2),
                    })}
                  </span>
                </div>
              </>
            )}
          </div>
        </BlurLoading>
      </section>

      {/* Quick Stats Bento */}
      <BlurLoading loading={isLoading}>
        <section className="grid grid-cols-2 gap-2">
        <Link
          to="/transactions?tipo=cobro&estado=pendiente"
          className="glass-panel flex aspect-[4/3] flex-col justify-between rounded-lg p-4 transition-transform hover:scale-[1.01] active:scale-[0.99]"
        >
          <div className="flex items-start justify-between">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-income/20">
              <ArrowDown className="h-4 w-4 text-income" />
            </div>
            <span className="rounded-full bg-income/10 px-2 py-0.5 text-xs font-semibold text-income">
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

        <div className="flex flex-col gap-2">
          <Link
            to="/transactions?tipo=pago&estado=pendiente"
            className="glass-panel flex flex-1 items-center justify-between rounded-lg p-3 transition-transform hover:scale-[1.01] active:scale-[0.99]"
          >
            <div className="flex items-center gap-2">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-expense/20">
                <ArrowUp className="h-3.5 w-3.5 text-expense" />
              </div>
              <span className="text-sm text-on-surface-variant">{t("common.toPay")}</span>
            </div>
            {isLoading ? (
              <Skeleton className="h-5 w-14" />
            ) : (
              <span className="text-sm font-semibold text-on-surface">
                {formatCompact(Number(data?.to_pay ?? 0), "USD")}
              </span>
            )}
          </Link>
          <Link
            to="/transactions?estado=retrasado"
            className="glass-panel flex flex-1 items-center justify-between rounded-lg border-error/30 p-3 transition-transform hover:scale-[1.01] active:scale-[0.99]"
          >
            <div className="flex items-center gap-2">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-status-delayed/20">
                <TriangleAlert className="h-3.5 w-3.5 text-status-delayed" />
              </div>
              <span className="text-sm text-status-delayed">{t("common.delayed")}</span>
            </div>
            {isLoading ? (
              <Skeleton className="h-5 w-14" />
            ) : (
              <span className="text-sm font-semibold text-on-surface">
                {formatCompact(Number(data?.overdue ?? 0), "USD")}
              </span>
            )}
          </Link>
        </div>
      </section>
      </BlurLoading>

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
          <div className="glass-panel rounded-lg p-6 text-center">
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
              <div className="glass-panel rounded-lg p-6 text-center text-sm text-on-surface-variant">
                {t("dashboard.noRecent")}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}