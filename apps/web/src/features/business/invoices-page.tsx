import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Plus, ReceiptText, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Segmented } from "@/components/ui/segmented";
import { useInvoices } from "@/hooks/use-queries";
import { formatMoney, formatDate } from "@/lib/format";
import type { Invoice, InvoiceStatus } from "@/lib/types";

export const INVOICE_STATUS_OPTIONS: Array<{ value: InvoiceStatus | ""; label: string }> = [
  { value: "", label: "invoices.statuses.all" },
  { value: "borrador", label: "invoices.statuses.borrador" },
  { value: "enviada", label: "invoices.statuses.enviada" },
  { value: "parcial", label: "invoices.statuses.parcial" },
  { value: "pagada", label: "invoices.statuses.pagada" },
  { value: "vencida", label: "invoices.statuses.vencida" },
  { value: "anulada", label: "invoices.statuses.anulada" },
];

const STATUS_VARIANT: Record<InvoiceStatus, "secondary" | "pending" | "warning" | "success" | "delayed" | "outline"> = {
  borrador: "secondary",
  enviada: "pending",
  parcial: "warning",
  pagada: "success",
  vencida: "delayed",
  anulada: "outline",
};

export function InvoiceStatusBadge({ status }: { status: InvoiceStatus }) {
  const { t } = useTranslation();
  return (
    <Badge variant={STATUS_VARIANT[status]}>{t(`invoices.statuses.${status}`)}</Badge>
  );
}

function InvoiceCard({ invoice }: { invoice: Invoice }) {
  const { t } = useTranslation();
  return (
    <Link
      to={`/business/invoices/${invoice.id}`}
      className="glass-panel clip-rounded-lg flex items-center justify-between gap-3 rounded-lg p-4 transition-transform hover:-translate-y-0.5"
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-on-surface">{invoice.number}</span>
          <InvoiceStatusBadge status={invoice.status} />
        </div>
        <div className="mt-1 truncate text-sm text-on-surface-variant">{invoice.contact.name}</div>
        <div className="text-xs text-on-surface-variant">
          {t("invoices.list.dueDate")}: {formatDate(invoice.due_date)}
        </div>
      </div>
      <div className="text-right shrink-0">
        <div className="text-sm font-semibold text-on-surface">
          {formatMoney(invoice.total, invoice.currency, { symbol: true })}
        </div>
        <div className="text-xs text-primary">
          {t("invoices.list.balance")}: {formatMoney(invoice.balance_due, invoice.currency)}
        </div>
      </div>
    </Link>
  );
}

export default function InvoicesPage() {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  useEffect(() => {
    const id = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(id);
  }, [search]);

  const { data, isLoading, isError } = useInvoices(debouncedSearch || undefined, statusFilter || undefined);
  const invoices = useMemo(() => data?.results ?? [], [data]);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
            <ReceiptText className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-on-surface">{t("invoices.title")}</h1>
            <p className="text-sm text-on-surface-variant">{t("invoices.subtitle")}</p>
          </div>
        </div>
        <Link to="/business/invoices/new">
          <Button variant="glow" className="gap-1">
            <Plus className="h-4 w-4" /> {t("invoices.new")}
          </Button>
        </Link>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-on-surface-variant" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("invoices.searchPlaceholder")}
            className="pl-9"
          />
        </div>
        <Segmented
          layoutId="seg-invoice-status"
          size="sm"
          options={INVOICE_STATUS_OPTIONS.map((o) => ({ value: o.value, label: t(o.label) }))}
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
      ) : invoices.length === 0 ? (
        <p className="glass-panel clip-rounded-lg rounded-lg p-8 text-center text-sm text-on-surface-variant">
          {t("invoices.empty")}
        </p>
      ) : (
        <div className="space-y-2">
          {invoices.map((inv) => (
            <InvoiceCard key={inv.id} invoice={inv} />
          ))}
        </div>
      )}
    </div>
  );
}