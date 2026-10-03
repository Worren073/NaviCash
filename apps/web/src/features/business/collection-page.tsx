import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ChevronRight, CheckCircle2, HandCoins, PhoneCall } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useInvoices } from "@/hooks/use-queries";
import { formatDate, formatMoney } from "@/lib/format";
import { FollowUpDialog } from "./follow-up-dialog";
import { InvoiceStatusBadge } from "./invoices-page";
import type { Invoice } from "@/lib/types";

const OPEN_STATUSES: Invoice["status"][] = ["enviada", "parcial", "vencida"];

function todayISO(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

function LatestChip({ invoice }: { invoice: Invoice }) {
  const { t } = useTranslation();
  const followUp = invoice.latest_follow_up;
  if (!followUp) return null;
  const label = `${t(`collection.channels.${followUp.channel}`)} · ${t(
    `collection.outcomes.${followUp.outcome}`
  )}`;
  return (
    <Badge variant="secondary" title={followUp.notes || undefined}>
      {t("collection.followUps.latest")}: {label}
    </Badge>
  );
}

export default function CollectionPage() {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useInvoices();
  const [recordFor, setRecordFor] = useState<Invoice | null>(null);

  const today = todayISO();
  const open = useMemo(
    () =>
      (data?.results ?? [])
        .filter((inv) => OPEN_STATUSES.includes(inv.status))
        .sort((a, b) => {
          const aOverdue = a.due_date < today ? 0 : 1;
          const bOverdue = b.due_date < today ? 0 : 1;
          return aOverdue - bOverdue || a.due_date.localeCompare(b.due_date);
        }),
    [data, today]
  );

  const receivable = useMemo(
    () => open.reduce((sum, inv) => sum + Number(inv.balance_due), 0),
    [open]
  );
  const overdue = useMemo(
    () => open.filter((inv) => inv.due_date < today).length,
    [open, today]
  );
  const currency = data?.results?.[0]?.currency ?? "USD";

  if (isError) {
    return (
      <p className="glass-panel clip-rounded-lg rounded-lg p-6 text-center text-sm text-on-surface-variant">
        {t("errors.generic")}
      </p>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
          <HandCoins className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-on-surface">{t("collection.title")}</h1>
          <p className="text-sm text-on-surface-variant">{t("collection.subtitle")}</p>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : open.length === 0 ? (
        <p className="glass-panel clip-rounded-lg flex flex-col items-center gap-2 rounded-lg p-10 text-center text-sm text-on-surface-variant">
          <CheckCircle2 className="h-8 w-8 text-income-text" />
          {t("collection.done")}
        </p>
      ) : (
        <>
          <section className="grid grid-cols-2 gap-2 md:gap-3">
            <div className="glass-panel clip-rounded-lg rounded-lg p-4">
              <span className="text-xs font-semibold text-on-surface-variant">
                {t("collection.totalReceivable")}
              </span>
              <div className="mt-1 text-2xl font-semibold text-on-surface">
                {formatMoney(receivable, currency, { symbol: true })}
              </div>
            </div>
            <div className="glass-panel clip-rounded-lg rounded-lg p-4">
              <span className="text-xs font-semibold text-on-surface-variant">
                {t("collection.overdueCount")}
              </span>
              <div className={`mt-1 text-2xl font-semibold ${overdue > 0 ? "text-delayed-text" : "text-income-text"}`}>
                {overdue}
              </div>
            </div>
          </section>

          <section className="space-y-2">
            {open.map((inv) => {
              const isOverdue = inv.due_date < today;
              return (
                <div
                  key={inv.id}
                  className="glass-panel clip-rounded-lg flex items-center justify-between gap-3 rounded-lg p-4"
                >
                  <Link
                    to={`/business/invoices/${inv.id}`}
                    className="min-w-0 flex-1 transition-opacity hover:opacity-80"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-on-surface">{inv.number}</span>
                      <InvoiceStatusBadge status={inv.status} />
                      {isOverdue && (
                        <Badge variant="delayed">{t("collection.overdueLabel")}</Badge>
                      )}
                    </div>
                    <div className="mt-1 truncate text-sm text-on-surface-variant">
                      {inv.contact.name}
                    </div>
                    <div
                      className={`text-xs ${isOverdue ? "text-delayed-text" : "text-on-surface-variant"}`}
                    >
                      {t("collection.dueDate")}: {formatDate(inv.due_date)}
                    </div>
                    <div className="mt-1">
                      <LatestChip invoice={inv} />
                    </div>
                  </Link>

                  <div className="flex shrink-0 flex-col items-end gap-2">
                    <div className="text-base font-semibold text-on-surface">
                      {formatMoney(inv.balance_due, inv.currency, { symbol: true })}
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1"
                      onClick={() => setRecordFor(inv)}
                    >
                      <PhoneCall className="h-3.5 w-3.5" /> {t("collection.register")}
                    </Button>
                    <Link
                      to={`/business/invoices/${inv.id}`}
                      className="text-xs text-primary transition-opacity hover:opacity-80"
                    >
                      {t("collection.followUps.detail")} <ChevronRight className="inline h-3 w-3" />
                    </Link>
                  </div>
                </div>
              );
            })}
          </section>
        </>
      )}

      <FollowUpDialog
        open={Boolean(recordFor)}
        onOpenChange={(open) => !open && setRecordFor(null)}
        invoiceId={recordFor?.id ?? ""}
      />
    </div>
  );
}