import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { sileo } from "sileo";
import {
  ArrowLeft,
  Banknote,
  Mail,
  Package,
  Phone,
  PhoneCall,
  ReceiptText,
  Trash2,
  XCircle,
  SendHorizontal,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { useFollowUps, useInvoice } from "@/hooks/use-queries";
import { queryKeys } from "@/hooks/use-queries";
import { api, ApiErrorClass } from "@/lib/api";
import { formatMoney, formatDate } from "@/lib/format";
import { InvoiceStatusBadge } from "./invoices-page";
import { FollowUpDialog } from "./follow-up-dialog";
import type { CollectionOutcome } from "@/lib/types";

const OUTCOME_VARIANT: Record<CollectionOutcome, "pending" | "warning" | "success" | "delayed" | "secondary"> = {
  sin_respuesta: "pending",
  promesa_pago: "warning",
  pago_realizado: "success",
  rechazado: "delayed",
  otro: "secondary",
};

export default function InvoiceDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();

  const { data: invoice, isLoading, isError } = useInvoice(id);
  const { data: followUpsData } = useFollowUps(id);
  const followUps = useMemo(() => followUpsData?.results ?? [], [followUpsData]);
  const [confirmSend, setConfirmSend] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [payOpen, setPayOpen] = useState(false);
  const [payAmount, setPayAmount] = useState("");
  const [payNote, setPayNote] = useState("");
  const [followUpOpen, setFollowUpOpen] = useState(false);

  const paid = useMemo(() => Number(invoice?.amount_paid ?? 0), [invoice]);
  const balanceDue = useMemo(() => Number(invoice?.balance_due ?? 0), [invoice]);

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.invoices }),
      queryClient.invalidateQueries({ queryKey: queryKeys.businessSummary }),
    ]);
  };

  const send = useMutation({
    mutationFn: () => api.post(`/business/invoices/${id}/send/`),
    onSuccess: () => {
      void refresh();
      setConfirmSend(false);
      sileo.success({ title: t("invoices.send") });
    },
    onError: (err) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("errors.generic");
      sileo.error({ title: msg });
    },
  });

  const cancel = useMutation({
    mutationFn: () => api.post(`/business/invoices/${id}/cancel/`),
    onSuccess: () => {
      void refresh();
      setConfirmCancel(false);
      sileo.success({ title: t("invoices.cancel") });
    },
    onError: (err) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("errors.generic");
      sileo.error({ title: msg });
    },
  });

  const pay = useMutation({
    mutationFn: () =>
      api.post(`/business/invoices/${id}/pay/`, {
        amount: payAmount,
        ...(payNote.trim() ? { note: payNote.trim() } : {}),
      }),
    onSuccess: () => {
      void refresh();
      setPayOpen(false);
      setPayAmount("");
      setPayNote("");
      sileo.success({ title: t("invoices.updated") });
    },
    onError: (err) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("errors.generic");
      sileo.error({ title: msg });
    },
  });

  const deleteFollowUp = useMutation({
    mutationFn: (followUpId: string) => api.delete(`/business/follow-ups/${followUpId}/`),
    onSuccess: () => {
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.followUps }),
        queryClient.invalidateQueries({ queryKey: queryKeys.invoices }),
      ]);
      sileo.success({ title: t("collection.followUps.deleted") });
    },
    onError: (err) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("errors.generic");
      sileo.error({ title: msg });
    },
  });

  if (isLoading) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (isError || !invoice) {
    return (
      <p className="glass-panel clip-rounded-lg rounded-lg p-6 text-center text-sm text-on-surface-variant">
        {t("errors.generic")}
      </p>
    );
  }

  const canSend = invoice.status === "borrador";
  const canCancel = invoice.status !== "anulada";
  const canPay = invoice.status === "enviada" || invoice.status === "parcial" || invoice.status === "vencida";

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <Link
          to="/business/invoices"
          className="mb-3 inline-flex items-center gap-1 text-sm text-primary transition-opacity hover:opacity-80"
        >
          <ArrowLeft className="h-4 w-4" /> {t("invoices.detail.back")}
        </Link>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-full bg-primary/10">
              <ReceiptText className="h-6 w-6 text-primary" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold text-on-surface">{invoice.number}</h1>
                <InvoiceStatusBadge status={invoice.status} />
              </div>
              <div className="flex flex-wrap gap-x-4 text-sm text-on-surface-variant">
                <span>
                  {t("invoices.detail.issueDate")}: {formatDate(invoice.issue_date)}
                </span>
                <span>
                  {t("invoices.detail.dueDate")}: {formatDate(invoice.due_date)}
                </span>
              </div>
            </div>
          </div>

          {invoice.status !== "pagada" && (
            <div className="flex flex-wrap gap-2">
              {canSend && (
                <Button
                  variant="glow"
                  size="sm"
                  className="gap-1"
                  disabled={send.isPending}
                  onClick={() => setConfirmSend(true)}
                >
                  <SendHorizontal className="h-4 w-4" /> {t("invoices.send")}
                </Button>
              )}
              {canPay && (
                <Button
                  variant="default"
                  size="sm"
                  className="gap-1"
                  onClick={() => {
                    setPayAmount(String(balanceDue));
                    setPayOpen(true);
                  }}
                >
                  <Banknote className="h-4 w-4" /> {t("invoices.pay")}
                </Button>
              )}
              {canCancel && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="gap-1"
                  disabled={cancel.isPending}
                  onClick={() => setConfirmCancel(true)}
                >
                  <XCircle className="h-4 w-4" /> {t("invoices.cancel")}
                </Button>
              )}
            </div>
          )}
        </div>
      </div>

      <section className="glass-panel clip-rounded-lg rounded-lg p-4">
        <div className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
          {t("invoices.detail.issuedTo")}
        </div>
        <div className="mt-1 text-base font-semibold text-on-surface">{invoice.contact.name}</div>
        <div className="mt-1 flex flex-wrap gap-x-4 text-sm text-on-surface-variant">
          {invoice.contact.email && (
            <span className="inline-flex items-center gap-1">
              <Mail className="h-3.5 w-3.5" /> {invoice.contact.email}
            </span>
          )}
          {invoice.contact.phone && (
            <span className="inline-flex items-center gap-1">
              <Phone className="h-3.5 w-3.5" /> {invoice.contact.phone}
            </span>
          )}
          {invoice.contact.customer_type && (
            <span>{t(`contacts.customerTypes.${invoice.contact.customer_type}`)}</span>
          )}
        </div>
      </section>

      <section className="glass-panel clip-rounded-lg overflow-hidden rounded-lg">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-glass-border text-left text-xs uppercase tracking-wider text-on-surface-variant">
                <th className="px-4 py-2 font-semibold">{t("invoices.detail.description")}</th>
                <th className="px-2 py-2 text-right font-semibold">{t("invoices.detail.qty")}</th>
                <th className="px-2 py-2 text-right font-semibold">{t("invoices.detail.price")}</th>
                <th className="px-2 py-2 text-right font-semibold">{t("invoices.detail.discount")}</th>
                <th className="px-4 py-2 text-right font-semibold">{t("invoices.detail.lineTotal")}</th>
              </tr>
            </thead>
            <tbody>
              {invoice.items.map((item) => (
                <tr key={item.id} className="border-b border-glass-border/60 last:border-b-0">
                  <td className="px-4 py-2.5 font-medium text-on-surface">
                    <div className="flex items-center gap-2">
                      {item.description}
                      {item.product && (
                        <Badge variant="secondary" className="gap-1">
                          <Package className="h-3 w-3" /> {t("inventory.catalogue")}
                        </Badge>
                      )}
                    </div>
                  </td>
                  <td className="px-2 py-2.5 text-right text-on-surface-variant">{item.quantity}</td>
                  <td className="px-2 py-2.5 text-right text-on-surface-variant">
                    {formatMoney(item.unit_price, invoice.currency)}
                  </td>
                  <td className="px-2 py-2.5 text-right text-on-surface-variant">
                    {Number(item.discount) > 0 ? formatMoney(item.discount, invoice.currency) : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-right font-semibold text-on-surface">
                    {formatMoney(item.total, invoice.currency)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex flex-col items-end gap-1 border-t border-glass-border px-4 py-3 text-sm">
          <div className="flex w-full max-w-xs justify-between text-on-surface-variant">
            <span>{t("invoices.detail.subtotal")}</span>
            <span>{formatMoney(invoice.subtotal, invoice.currency)}</span>
          </div>
          <div className="flex w-full max-w-xs justify-between text-on-surface-variant">
            <span>{t("invoices.detail.tax")}</span>
            <span>{formatMoney(invoice.tax_amount, invoice.currency)}</span>
          </div>
          <div className="flex w-full max-w-xs justify-between border-t border-glass-border pt-1 text-base font-semibold text-on-surface">
            <span>{t("invoices.detail.total")}</span>
            <span>{formatMoney(invoice.total, invoice.currency)}</span>
          </div>
          <div className="flex w-full max-w-xs justify-between text-on-surface-variant">
            <span>{t("invoices.detail.amountPaid")}</span>
            <span className="text-income-text">{formatMoney(paid, invoice.currency)}</span>
          </div>
          <div className="flex w-full max-w-xs justify-between font-medium">
            <span className="text-on-surface">{t("invoices.detail.balanceDue")}</span>
            <span className={balanceDue > 0 ? "text-warning-text" : "text-income-text"}>
              {formatMoney(balanceDue, invoice.currency)}
            </span>
          </div>
        </div>
      </section>

      {invoice.payments.length > 0 && (
        <section className="glass-panel clip-rounded-lg rounded-lg p-4">
          <h2 className="text-sm font-semibold text-on-surface">{t("invoices.detail.payments")}</h2>
          <div className="mt-2 space-y-2">
            {invoice.payments.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between rounded-lg bg-surface-container-high px-3 py-2"
              >
                <div>
                  <div className="text-sm font-medium text-on-surface">
                    {formatMoney(p.amount, invoice.currency)}
                  </div>
                  <div className="text-xs text-on-surface-variant">
                    {formatDate(p.paid_at)}
                    {p.note ? ` · ${p.note}` : ""}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {invoice.notes && (
        <section className="glass-panel clip-rounded-lg rounded-lg p-4">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
            {t("invoices.detail.notes")}
          </h2>
          <p className="mt-1 text-sm text-on-surface">{invoice.notes}</p>
        </section>
      )}

      <section className="glass-panel clip-rounded-lg rounded-lg p-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-on-surface">
            {t("collection.followUps.history")}
          </h2>
          <Button
            variant="outline"
            size="sm"
            className="gap-1"
            onClick={() => setFollowUpOpen(true)}
          >
            <PhoneCall className="h-3.5 w-3.5" /> {t("collection.followUps.record")}
          </Button>
        </div>
        {followUps.length === 0 ? (
          <p className="mt-2 text-sm text-on-surface-variant">
            {t("collection.followUps.emptyHistory")}
          </p>
        ) : (
          <div className="mt-2 space-y-2">
            {followUps.map((followUp) => (
              <div
                key={followUp.id}
                className="flex items-start justify-between gap-2 rounded-lg bg-surface-container-high px-3 py-2"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="secondary">
                      {t(`collection.channels.${followUp.channel}`)}
                    </Badge>
                    <Badge variant={OUTCOME_VARIANT[followUp.outcome]}>
                      {t(`collection.outcomes.${followUp.outcome}`)}
                    </Badge>
                    {followUp.promised_date && (
                      <span className="text-xs text-on-surface-variant">
                        {t("collection.promised")}: {formatDate(followUp.promised_date)}
                      </span>
                    )}
                  </div>
                  <div className="mt-1 truncate text-xs text-on-surface-variant">
                    {formatDate(followUp.created_at)}
                    {followUp.notes ? ` · ${followUp.notes}` : ""}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => deleteFollowUp.mutate(followUp.id)}
                  disabled={deleteFollowUp.isPending}
                  className="text-on-surface-variant transition-colors hover:text-destructive"
                  aria-label={t("common.delete")}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      <Dialog open={confirmSend} onOpenChange={setConfirmSend}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>
              {t("invoices.confirm.sendTitle", { number: invoice.number })}
            </DialogTitle>
            <DialogDescription>{t("invoices.confirm.sendMessage")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmSend(false)}>
              {t("common.cancel")}
            </Button>
            <Button variant="glow" onClick={() => send.mutate()} disabled={send.isPending}>
              {send.isPending ? t("invoices.sending") : t("invoices.send")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmCancel} onOpenChange={setConfirmCancel}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>
              {t("invoices.confirm.cancelTitle", { number: invoice.number })}
            </DialogTitle>
            <DialogDescription>{t("invoices.confirm.cancelMessage")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmCancel(false)}>
              {t("common.cancel")}
            </Button>
            <Button variant="destructive" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
              {cancel.isPending ? t("invoices.canceling") : t("invoices.cancel")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={payOpen} onOpenChange={setPayOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t("invoices.confirm.payTitle")}</DialogTitle>
            <DialogDescription>{t("invoices.detail.payHint")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-on-surface">
                {t("invoices.detail.payAmount")} ({t("invoices.detail.payMax")}{" "}
                {formatMoney(balanceDue, invoice.currency)})
              </span>
              <Input
                type="number"
                inputMode="decimal"
                value={payAmount}
                onChange={(e) => setPayAmount(e.target.value)}
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-on-surface">
                {t("invoices.detail.payNote")}
              </span>
              <Input value={payNote} onChange={(e) => setPayNote(e.target.value)} />
            </label>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setPayOpen(false)} disabled={pay.isPending}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="glow"
              onClick={() => pay.mutate()}
              disabled={!payAmount || Number(payAmount) <= 0 || pay.isPending}
            >
              {pay.isPending ? t("invoices.paying") : t("invoices.pay")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <FollowUpDialog
        open={followUpOpen}
        onOpenChange={setFollowUpOpen}
        invoiceId={invoice.id}
        onRegistered={() => void refresh()}
      />
    </div>
  );
}