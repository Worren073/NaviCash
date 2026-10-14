import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, ReceiptText, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import { Segmented } from "@/components/ui/segmented";
import { SidePanel, SidePanelContent, SidePanelTitle } from "@/components/ui/side-panel";
import { useInvoices } from "@/hooks/use-queries";
import { formatMoney, formatDate } from "@/lib/format";
import type { Invoice } from "@/lib/types";
import { INVOICE_STATUS_OPTIONS, InvoiceStatusBadge } from "./invoice-badges";
import { InvoiceDetail } from "./invoice-detail";
import { InvoiceForm } from "./invoice-new-page";

export { INVOICE_STATUS_OPTIONS, InvoiceStatusBadge } from "./invoice-badges";

function InvoiceCard({ invoice, onOpen }: { invoice: Invoice; onOpen: () => void }) {
  const { t } = useTranslation();
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
      className="glass-panel clip-rounded-lg flex cursor-pointer items-center justify-between gap-3 rounded-lg p-4 transition-transform hover:-translate-y-0.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
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
    </div>
  );
}

export default function InvoicesPage() {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState<Invoice | null>(null);
  const [formOpen, setFormOpen] = useState(false);

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
        <Button variant="glow" className="gap-1" onClick={() => setFormOpen(true)}>
          <Plus className="h-4 w-4" /> {t("invoices.new")}
        </Button>
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
          {invoices.map((inv, index) => (
            <Reveal key={inv.id} delay={Math.min(index, 6) * 0.1}>
              <InvoiceCard invoice={inv} onOpen={() => setSelected(inv)} />
            </Reveal>
          ))}
        </div>
      )}

      <SidePanel open={Boolean(selected)} onOpenChange={(open) => !open && setSelected(null)}>
        <SidePanelContent>
          {selected && <SidePanelTitle className="sr-only">{selected.number}</SidePanelTitle>}
          {selected && <InvoiceDetail id={selected.id} />}
        </SidePanelContent>
      </SidePanel>

      <SidePanel open={formOpen} onOpenChange={setFormOpen}>
        <SidePanelContent size="wide">
          {formOpen && (
            <SidePanelTitle className="sr-only">{t("invoices.form.title")}</SidePanelTitle>
          )}
          {formOpen && (
            <InvoiceForm
              onCancel={() => setFormOpen(false)}
              onCreated={(invoice) => {
                setFormOpen(false);
                setSelected(invoice);
              }}
            />
          )}
        </SidePanelContent>
      </SidePanel>
    </div>
  );
}