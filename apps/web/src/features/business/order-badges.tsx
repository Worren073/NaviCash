import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import type { Order, OrderPaymentState, OrderStatus } from "@/lib/types";

export const ORDER_STATUS_OPTIONS: Array<{ value: OrderStatus | ""; label: string }> = [
  { value: "", label: "orders.statuses.all" },
  { value: "borrador", label: "orders.statuses.borrador" },
  { value: "en_camino", label: "orders.statuses.en_camino" },
  { value: "recibido", label: "orders.statuses.recibido" },
  { value: "anulado", label: "orders.statuses.anulado" },
];

const STATUS_VARIANT: Record<
  OrderStatus,
  "secondary" | "pending" | "success" | "warning" | "outline"
> = {
  borrador: "secondary",
  en_camino: "pending",
  recibido: "warning",
  anulado: "outline",
};

export function OrderStatusBadge({ status }: { status: OrderStatus }) {
  const { t } = useTranslation();
  return <Badge variant={STATUS_VARIANT[status]}>{t(`orders.statuses.${status}`)}</Badge>;
}

export function OrderPaymentBadge({ paymentState }: { paymentState: OrderPaymentState }) {
  const { t } = useTranslation();
  if (paymentState === "none") return null;
  return (
    <Badge variant={paymentState === "paid" ? "success" : "pending"}>
      {t(paymentState === "paid" ? "orders.statuses.paid" : "orders.statuses.partial")}
    </Badge>
  );
}

export function OrderStatusCluster({ order }: { order: Order }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <OrderStatusBadge status={order.status} />
      <OrderPaymentBadge paymentState={order.payment_state} />
    </span>
  );
}
