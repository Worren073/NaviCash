import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ReceiptText, Store, Wrench, PersonStanding, ArrowLeftRight } from "lucide-react";
import { CheckedIcon, XIcon } from "@/components/icons";

import { api, ApiErrorClass } from "@/lib/api";
import { queryKeys } from "@/hooks/use-queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { BlurLoading } from "@/components/ui/blur-loading";
import { formatMoney, formatRelativeEvent } from "@/lib/format";
import { Segmented } from "@/components/ui/segmented";
import type { Paginated, Transaction, TxState, TxType } from "@/lib/types";

const STATE_BADGE: Record<TxState, "success" | "pending" | "delayed" | "secondary"> = {
  pagado: "success",
  pendiente: "pending",
  retrasado: "delayed",
  cancelado: "secondary",
};

const STATUS_COLOR: Record<TxState, string> = {
  pagado: "#2dd4bf",
  pendiente: "#fbbf24",
  retrasado: "#f43f5e",
  cancelado: "#94a3b8",
};

function withAlpha(hex: string, alpha: number): string {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function TxIcon({ concepto }: { concepto: string }) {
  if (/servicio|técnic/i.test(concepto)) return <Wrench className="h-5 w-5" />;
  if (/mar[ií]a|carlos|pedro|ana|jos[eé]|luis/i.test(concepto))
    return <PersonStanding className="h-5 w-5" />;
  return <Store className="h-5 w-5" />;
}

function TxCard({ tx }: { tx: Transaction }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const setState = useMutation({
    mutationFn: (estado: "pagado" | "cancelado" | "pendiente") =>
      api.post<{ detail: string }>(`/transactions/${tx.id}/state`, { estado }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.transactions });
      void queryClient.invalidateQueries({ queryKey: queryKeys.overview });
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) setError(err.message);
      else setError(t("errors.generic"));
    },
  });

  const isIncome = tx.tipo === "cobro";
  const isTransfer = tx.tipo === "transferencia";
  const estado = tx.effective_state ?? tx.estado;
  const color = isTransfer ? "#0891b2" : STATUS_COLOR[estado];

  return (
    <div
      className="flex items-center justify-between rounded-lg border p-4 backdrop-blur-xl"
      style={{
        background: `linear-gradient(135deg, ${withAlpha(color, 0.22)}, ${withAlpha(color, 0.08)})`,
        borderColor: withAlpha(color, 0.35),
        boxShadow: `inset 0 1px 0 rgba(255,255,255,0.6), 0 4px 16px ${withAlpha(color, 0.12)}`,
      }}
    >
      <div className="flex min-w-0 items-center gap-3">
        <div
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full"
          style={{ backgroundColor: withAlpha(color, 0.25), color }}
        >
          {isTransfer ? (
            <ArrowLeftRight className="h-5 w-5" />
          ) : (
            <TxIcon concepto={tx.concepto} />
          )}
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-on-surface">
            {isTransfer ? t("wallet.transferRowLabel") : tx.concepto}
          </div>
          <div className="text-xs text-on-surface-variant">
            {isTransfer
              ? `${tx.wallet_name ?? ""} → ${tx.dest_wallet_name ?? ""}`
              : `${tx.wallet_name ?? ""} · ${formatRelativeEvent(tx.created_at)}`}
          </div>
        </div>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        <div className={`text-sm font-semibold ${isIncome ? "text-income" : "text-on-surface"}`}>
          {isTransfer
            ? formatMoney(tx.monto, tx.moneda, { symbol: true })
            : `${isIncome ? "+" : "-"}${formatMoney(tx.monto, tx.moneda, { symbol: true })}`}
        </div>
        {isTransfer ? (
          <span className="text-xs font-medium text-on-surface-variant">
            {tx.moneda_destino && tx.moneda_destino !== tx.moneda
              ? formatMoney(tx.monto_destino, tx.moneda_destino, { symbol: true })
              : ""}
          </span>
        ) : (
          <Badge variant={STATE_BADGE[estado]}>{t(`common.${estado}`)}</Badge>
        )}
        {tx.estado === "pendiente" && (
          <div className="mt-1 flex gap-1">
            <Button
              size="sm"
              variant="secondary"
              className="h-7 gap-1 px-2 text-xs"
              disabled={setState.isPending}
              onClick={() => setState.mutate("pagado")}
            >
              <CheckedIcon size={14} /> {t("common.pagado")}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 gap-1 px-2 text-xs"
              disabled={setState.isPending}
              onClick={() => setState.mutate("cancelado")}
            >
              <XIcon size={14} /> {t("common.cancel")}
            </Button>
          </div>
        )}
        {error && <span className="text-xs text-status-delayed">{error}</span>}
      </div>
    </div>
  );
}

export default function TransactionsPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [tipoFilter, setTipoFilter] = useState<TxType | "">(
    () => (searchParams.get("tipo") as TxType | "") ?? ""
  );
  const [estadoFilter, setEstadoFilter] = useState(
    () => searchParams.get("estado") ?? ""
  );
  const [fechaFilter, setFechaFilter] = useState(
    () => searchParams.get("fecha") ?? ""
  );
  const [page, setPage] = useState(() => {
    const p = Number(searchParams.get("page"));
    return Number.isFinite(p) && p > 0 ? p : 1;
  });

  useEffect(() => {
    const params = new URLSearchParams();
    if (tipoFilter) params.set("tipo", tipoFilter);
    if (estadoFilter) params.set("estado", estadoFilter);
    if (fechaFilter) params.set("fecha", fechaFilter);
    if (page > 1) params.set("page", String(page));
    if (params.toString() !== searchParams.toString()) {
      setSearchParams(params, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tipoFilter, estadoFilter, fechaFilter, page]);

  const { data, isLoading, isError } = useQuery({
    queryKey: [
      ...queryKeys.transactions,
      { tipo: tipoFilter, estado: estadoFilter, fecha: fechaFilter, page },
    ],
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("page_size", "5");
      params.set("page", String(page));
      if (tipoFilter) params.set("tipo", tipoFilter);
      if (estadoFilter) params.set("estado", estadoFilter);
      if (fechaFilter) params.set("fecha", fechaFilter);
      return api.get<Paginated<Transaction>>(`/transactions?${params.toString()}`);
    },
  });

  const totalPages = Math.max(1, Math.ceil((data?.count ?? 0) / 5));
  const results = data?.results ?? [];

  const changeTipo = (value: TxType | "") => {
    setTipoFilter(value);
    setPage(1);
  };

  const changeEstado = (value: string) => {
    setEstadoFilter(value);
    setPage(1);
  };

  const changeFecha = (value: string) => {
    setFechaFilter(value);
    setPage(1);
  };

  return (
    <div className="mt-4 space-y-4">
      <div className="mb-4 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
          <ReceiptText className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h2 className="text-2xl font-bold text-on-surface">{t("transactions.title")}</h2>
          <p className="text-sm text-on-surface-variant">{t("transactions.subtitle")}</p>
        </div>
      </div>

      {/* Filtro tipo cobro/pago */}
      <Segmented
        layoutId="seg-tipo-list"
        options={[
          { value: "", label: t("transactions.allTypes") },
          { value: "cobro", label: t("addOperation.typeCobro") },
          { value: "pago", label: t("addOperation.typePago") },
        ]}
        value={tipoFilter}
        onChange={changeTipo}
      />

      {/* Filtros */}
      <div className="flex gap-2">
        <select
          value={estadoFilter}
          onChange={(e) => changeEstado(e.target.value)}
          aria-label={t("transactions.filterState")}
          className="h-11 min-w-0 flex-1 rounded-xl border border-glass-border bg-glass-surface px-3 text-sm text-on-surface shadow-sm outline-none transition-colors backdrop-blur-md focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30"
        >
          <option value="">{t("transactions.allStates")}</option>
          {(["pendiente", "pagado", "retrasado", "cancelado"] as const).map((s) => (
            <option key={s} value={s}>
              {t(`common.${s}`)}
            </option>
          ))}
        </select>
        <input
          type="date"
          value={fechaFilter}
          onChange={(e) => changeFecha(e.target.value)}
          aria-label={t("transactions.filterDate")}
          className="h-11 min-w-0 flex-1 rounded-xl border border-glass-border bg-glass-surface px-3 text-sm text-on-surface shadow-sm outline-none transition-colors backdrop-blur-md focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30"
        />
      </div>

      <BlurLoading loading={isLoading}>
        {isError ? (
          <p className="glass-panel rounded-lg p-6 text-center text-sm text-on-surface-variant">
            {t("errors.generic")}
          </p>
        ) : isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : results.length === 0 ? (
          <p className="glass-panel rounded-lg p-6 text-center text-sm text-on-surface-variant">
            {tipoFilter || estadoFilter || fechaFilter
              ? t("transactions.noResults")
              : t("transactions.empty")}
          </p>
        ) : (
          <div className="space-y-2">
            {results.map((tx) => (
              <TxCard key={tx.id} tx={tx} />
            ))}
          </div>
        )}
      </BlurLoading>

      {(data?.count ?? 0) > 5 && (
        <div className="flex items-center justify-center gap-3 pt-1">
          <Button
            size="sm"
            variant="outline"
            disabled={page <= 1 || isLoading}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            {t("common.prev")}
          </Button>
          <span className="text-sm text-on-surface-variant">
            {t("transactions.pageOf", { page, total: totalPages })}
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={page >= totalPages || isLoading}
            onClick={() => setPage((p) => p + 1)}
          >
            {t("common.next")}
          </Button>
        </div>
      )}
    </div>
  );
}