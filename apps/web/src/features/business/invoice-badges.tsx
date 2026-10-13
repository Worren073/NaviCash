import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import type { InvoiceStatus } from "@/lib/types";

export const INVOICE_STATUS_OPTIONS: Array<{ value: InvoiceStatus | ""; label: string }> = [
  { value: "", label: "invoices.statuses.all" },
  { value: "borrador", label: "invoices.statuses.borrador" },
  { value: "enviada", label: "invoices.statuses.enviada" },
  { value: "parcial", label: "invoices.statuses.parcial" },
  { value: "pagada", label: "invoices.statuses.pagada" },
  { value: "vencida", label: "invoices.statuses.vencida" },
  { value: "anulada", label: "invoices.statuses.anulada" },
];

const STATUS_VARIANT: Record<
  InvoiceStatus,
  "secondary" | "pending" | "warning" | "success" | "delayed" | "outline"
> = {
  borrador: "secondary",
  enviada: "pending",
  parcial: "warning",
  pagada: "success",
  vencida: "delayed",
  anulada: "outline",
};

export function InvoiceStatusBadge({ status }: { status: InvoiceStatus }) {
  const { t } = useTranslation();
  return <Badge variant={STATUS_VARIANT[status]}>{t(`invoices.statuses.${status}`)}</Badge>;
}
