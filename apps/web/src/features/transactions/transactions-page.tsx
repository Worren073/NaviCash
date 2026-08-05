import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ReceiptText, Store, Wrench, PersonStanding } from "lucide-react";
import { CheckedIcon, XIcon } from "@/components/icons";

import { api, ApiErrorClass } from "@/lib/api";
import { queryKeys } from "@/hooks/use-queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { BlurLoading } from "@/components/ui/blur-loading";
import { formatMoney, formatRelativeEvent } from "@/lib/format";
import type { Paginated, Transaction, TxState } from "@/lib/types";

const STATE_BADGE: Record<TxState, "success" | "pending" | "delayed" | "secondary"> = {
  pagado: "success",
  pendiente: "pending",
  retrasado: "delayed",
  cancelado: "secondary",
};

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

  return (
    <div className="glass-panel flex items-center justify-between rounded-lg p-4">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-surface-container-high text-on-surface-variant">
          <TxIcon concepto={tx.concepto} />
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-on-surface">{tx.concepto}</div>
          <div className="text-xs text-on-surface-variant">
            {tx.wallet_name ?? ""} · {formatRelativeEvent(tx.created_at)}
          </div>
        </div>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        <div className={`text-sm font-semibold ${isIncome ? "text-income" : "text-on-surface"}`}>
          {isIncome ? "+" : "-"}
          {formatMoney(tx.monto, tx.moneda, { symbol: true })}
        </div>
        <Badge variant={STATE_BADGE[tx.estado]}>{t(`common.${tx.estado}`)}</Badge>
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
  const { data, isLoading, isError } = useQuery({
    queryKey: queryKeys.transactions,
    queryFn: () =>
      api.get<Paginated<Transaction>>("/transactions").then((d) => d.results),
  });

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
        ) : (data ?? []).length === 0 ? (
          <p className="glass-panel rounded-lg p-6 text-center text-sm text-on-surface-variant">
            {t("transactions.empty")}
          </p>
        ) : (
          <div className="space-y-2">
            {(data ?? []).map((tx) => (
              <TxCard key={tx.id} tx={tx} />
            ))}
          </div>
        )}
      </BlurLoading>
    </div>
  );
}