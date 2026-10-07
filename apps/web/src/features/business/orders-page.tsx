import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Plus, Search, ShoppingCart } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Segmented } from "@/components/ui/segmented";
import { useOrders } from "@/hooks/use-queries";
import { formatMoney, formatDate } from "@/lib/format";
import type { Order, OrderStatus } from "@/lib/types";

export const ORDER_STATUS_OPTIONS: Array<{ value: OrderStatus | ""; label: string }> = [
  { value: "", label: "orders.statuses.all" },
  { value: "borrador", label: "orders.statuses.borrador" },
  { value: "en_camino", label: "orders.statuses.en_camino" },
  { value: "pagado", label: "orders.statuses.pagado" },
  { value: "recibido", label: "orders.statuses.recibido" },
  { value: "anulado", label: "orders.statuses.anulado" },
];

const STATUS_VARIANT: Record<OrderStatus, "secondary" | "pending" | "success" | "warning" | "outline"> = {
  borrador: "secondary",
  en_camino: "pending",
  pagado: "success",
  recibido: "warning",
  anulado: "outline",
};

export function OrderStatusBadge({ status }: { status: OrderStatus }) {
  const { t } = useTranslation();
  return (
    <Badge variant={STATUS_VARIANT[status]}>{t(`orders.statuses.${status}`)}</Badge>
  );
}

function OrderCard({ order }: { order: Order }) {
  const { t } = useTranslation();
  return (
    <Link
      to={`/business/orders/${order.id}`}
      className="glass-panel clip-rounded-lg flex items-center justify-between gap-3 rounded-lg p-4 transition-transform hover:-translate-y-0.5"
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-on-surface">{order.number}</span>
          <OrderStatusBadge status={order.status} />
        </div>
        <div className="mt-1 truncate text-sm text-on-surface-variant">{order.contact.name}</div>
        <div className="text-xs text-on-surface-variant">
          {t("orders.list.orderDate")}: {formatDate(order.order_date)}
        </div>
      </div>
      <div className="text-right shrink-0">
        <div className="text-sm font-semibold text-on-surface">
          {formatMoney(order.total, order.currency, { symbol: true })}
        </div>
        <div className="text-xs text-expense">
          {t("orders.list.balance")}: {formatMoney(order.balance_due, order.currency)}
        </div>
      </div>
    </Link>
  );
}

export default function OrdersPage() {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  useEffect(() => {
    const id = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(id);
  }, [search]);

  const { data, isLoading, isError } = useOrders(debouncedSearch || undefined, statusFilter || undefined);
  const orders = useMemo(() => data?.results ?? [], [data]);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
            <ShoppingCart className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-on-surface">{t("orders.title")}</h1>
            <p className="text-sm text-on-surface-variant">{t("orders.subtitle")}</p>
          </div>
        </div>
        <Link to="/business/orders/new">
          <Button variant="glow" className="gap-1">
            <Plus className="h-4 w-4" /> {t("orders.new")}
          </Button>
        </Link>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-on-surface-variant" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("orders.searchPlaceholder")}
            className="pl-9"
          />
        </div>
        <Segmented
          layoutId="seg-order-status"
          size="sm"
          options={ORDER_STATUS_OPTIONS.map((o) => ({ value: o.value, label: t(o.label) }))}
          value={statusFilter}
          onChange={setStatusFilter}
        />
      </div>

      {isError ? (
        <p className="glass-panel clip-rounded-lg rounded-lg p-6 text-center text-sm text-on-surface-variant">
          {t("errors.generic")}
        </p>
      ) : isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : orders.length === 0 ? (
        <p className="glass-panel clip-rounded-lg rounded-lg p-8 text-center text-sm text-on-surface-variant">
          {t("orders.empty")}
        </p>
      ) : (
        <div className="space-y-2">
          {orders.map((order) => (
            <OrderCard key={order.id} order={order} />
          ))}
        </div>
      )}
    </div>
  );
}