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
  PackagePlus,
  Phone,
  ShoppingCart,
  Users,
  XCircle,
  SendHorizontal,
  Truck,
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
import { NumericInput } from "@/components/ui/numeric-input";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { useOrder } from "@/hooks/use-queries";
import { queryKeys } from "@/hooks/use-queries";
import { api, ApiErrorClass } from "@/lib/api";
import { formatMoney, formatDate } from "@/lib/format";
import { OrderStatusCluster } from "./orders-page";

export default function OrderDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();

  const { data: order, isLoading, isError } = useOrder(id);
  const [confirmSend, setConfirmSend] = useState(false);
  const [confirmReceive, setConfirmReceive] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [payOpen, setPayOpen] = useState(false);
  const [payAmount, setPayAmount] = useState("");
  const [payNote, setPayNote] = useState("");

  const balanceDue = useMemo(() => Number(order?.balance_due ?? 0), [order]);

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.orders }),
      queryClient.invalidateQueries({ queryKey: queryKeys.businessSummary }),
      queryClient.invalidateQueries({ queryKey: queryKeys.products }),
      queryClient.invalidateQueries({ queryKey: queryKeys.notifications }),
    ]);
  };

  const send = useMutation({
    mutationFn: () => api.post(`/business/orders/${id}/send/`),
    onSuccess: () => {
      void refresh();
      setConfirmSend(false);
      sileo.success({ title: t("orders.send") });
    },
    onError: (err) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("errors.generic");
      sileo.error({ title: msg });
    },
  });

  const receive = useMutation({
    mutationFn: () => api.post(`/business/orders/${id}/receive/`),
    onSuccess: () => {
      void refresh();
      setConfirmReceive(false);
      sileo.success({ title: t("orders.receive") });
    },
    onError: (err) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("errors.generic");
      sileo.error({ title: msg });
    },
  });

  const cancel = useMutation({
    mutationFn: () => api.post(`/business/orders/${id}/cancel/`),
    onSuccess: () => {
      void refresh();
      setConfirmCancel(false);
      sileo.success({ title: t("orders.cancel") });
    },
    onError: (err) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("errors.generic");
      sileo.error({ title: msg });
    },
  });

  const pay = useMutation({
    mutationFn: () =>
      api.post(`/business/orders/${id}/pay/`, {
        amount: payAmount,
        ...(payNote.trim() ? { note: payNote.trim() } : {}),
      }),
    onSuccess: () => {
      void refresh();
      setPayOpen(false);
      setPayAmount("");
      setPayNote("");
      sileo.success({ title: t("orders.updated") });
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

  if (isError || !order) {
    return (
      <p className="glass-panel clip-rounded-lg rounded-lg p-6 text-center text-sm text-on-surface-variant">
        {t("errors.generic")}
      </p>
    );
  }

  const canSend = order.status === "borrador";
  const canReceive = order.status !== "recibido" && order.status !== "anulado";
  const canPay =
    order.status !== "recibido" &&
    order.status !== "anulado" &&
    Number(order.balance_due) > 0;
  const canCancel = order.status !== "recibido" && order.status !== "anulado";

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <Link
          to="/business/orders"
          className="mb-3 inline-flex items-center gap-1 text-sm text-primary transition-opacity hover:opacity-80"
        >
          <ArrowLeft className="h-4 w-4" /> {t("orders.detail.back")}
        </Link>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-full bg-primary/10">
              <ShoppingCart className="h-6 w-6 text-primary" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold text-on-surface">{order.number}</h1>
                <OrderStatusCluster order={order} />
              </div>
              <div className="flex flex-wrap gap-x-4 text-sm text-on-surface-variant">
                <span>
                  {t("orders.detail.orderDate")}: {formatDate(order.order_date)}
                </span>
                {order.due_date && (
                  <span>
                    {t("orders.detail.dueDate")}: {formatDate(order.due_date)}
                  </span>
                )}
                {order.received_at && (
                  <span>
                    {t("orders.detail.receivedAt")}: {formatDate(order.received_at)}
                  </span>
                )}
              </div>
            </div>
          </div>

          {order.status !== "recibido" && order.status !== "anulado" && (
            <div className="flex flex-wrap gap-2">
              {canSend && (
                <Button
                  variant="glow"
                  size="sm"
                  className="gap-1"
                  disabled={send.isPending}
                  onClick={() => setConfirmSend(true)}
                >
                  <SendHorizontal className="h-4 w-4" /> {t("orders.send")}
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
                  <Banknote className="h-4 w-4" /> {t("orders.pay")}
                </Button>
              )}
              {canReceive && (
                <Button
                  variant="default"
                  size="sm"
                  className="gap-1"
                  disabled={receive.isPending}
                  onClick={() => setConfirmReceive(true)}
                >
                  <Truck className="h-4 w-4" /> {t("orders.receive")}
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
                  <XCircle className="h-4 w-4" /> {t("orders.cancel")}
                </Button>
              )}
            </div>
          )}
        </div>
      </div>

      <section className="glass-panel clip-rounded-lg rounded-lg p-4">
        <div className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
          {t("orders.detail.suppliedBy")}
        </div>
        <div className="mt-1 flex items-center gap-2 text-base font-semibold text-on-surface">
          <Users className="h-4 w-4 text-on-surface-variant" />
          {order.contact.name}
        </div>
        <div className="mt-1 flex flex-wrap gap-x-4 text-sm text-on-surface-variant">
          {order.contact.email && (
            <span className="inline-flex items-center gap-1">
              <Mail className="h-3.5 w-3.5" /> {order.contact.email}
            </span>
          )}
          {order.contact.phone && (
            <span className="inline-flex items-center gap-1">
              <Phone className="h-3.5 w-3.5" /> {order.contact.phone}
            </span>
          )}
        </div>
      </section>

      <section className="glass-panel clip-rounded-lg overflow-hidden rounded-lg">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-glass-border text-left text-xs uppercase tracking-wider text-on-surface-variant">
                <th className="px-4 py-2 font-semibold">{t("orders.detail.description")}</th>
                <th className="px-2 py-2 text-right font-semibold">{t("orders.detail.qty")}</th>
                <th className="px-2 py-2 text-right font-semibold">{t("orders.detail.price")}</th>
                <th className="px-2 py-2 text-right font-semibold">{t("orders.detail.discount")}</th>
                <th className="px-4 py-2 text-right font-semibold">{t("orders.detail.lineTotal")}</th>
              </tr>
            </thead>
            <tbody>
              {order.items.map((item) => (
                <tr key={item.id} className="border-b border-glass-border/60 last:border-b-0">
                  <td className="px-4 py-2.5 font-medium text-on-surface">
                    <div className="flex items-center gap-2">
                      {item.description}
                      {item.product ? (
                        <Badge variant="secondary" className="gap-1">
                          <Package className="h-3 w-3" /> {t("orders.detail.existingProduct")}
                        </Badge>
                      ) : (
                        <Badge variant="warning" className="gap-1">
                          <PackagePlus className="h-3 w-3" /> {t("orders.detail.newProduct")}
                        </Badge>
                      )}
                    </div>
                  </td>
                  <td className="px-2 py-2.5 text-right text-on-surface-variant">{item.quantity}</td>
                  <td className="px-2 py-2.5 text-right text-on-surface-variant">
                    {formatMoney(item.unit_price, order.currency)}
                  </td>
                  <td className="px-2 py-2.5 text-right text-on-surface-variant">
                    {Number(item.discount) > 0 ? formatMoney(item.discount, order.currency) : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-right font-semibold text-on-surface">
                    {formatMoney(item.total, order.currency)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex flex-col items-end gap-1 border-t border-glass-border px-4 py-3 text-sm">
          <div className="flex w-full max-w-xs justify-between text-on-surface-variant">
            <span>{t("orders.detail.subtotal")}</span>
            <span>{formatMoney(order.subtotal, order.currency)}</span>
          </div>
          <div className="flex w-full max-w-xs justify-between text-on-surface-variant">
            <span>{t("orders.detail.shipping")}</span>
            <span>{formatMoney(order.shipping_amount, order.currency)}</span>
          </div>
          <div className="flex w-full max-w-xs justify-between border-t border-glass-border pt-1 text-base font-semibold text-on-surface">
            <span>{t("orders.detail.total")}</span>
            <span>{formatMoney(order.total, order.currency)}</span>
          </div>
          <div className="flex w-full max-w-xs justify-between text-on-surface-variant">
            <span>{t("orders.detail.amountPaid")}</span>
            <span className="text-income-text">{formatMoney(order.amount_paid, order.currency)}</span>
          </div>
          <div className="flex w-full max-w-xs justify-between font-medium">
            <span className="text-on-surface">{t("orders.detail.balanceDue")}</span>
            <span className={balanceDue > 0 ? "text-warning-text" : "text-income-text"}>
              {formatMoney(balanceDue, order.currency)}
            </span>
          </div>
        </div>
      </section>

      {order.payments.length > 0 && (
        <section className="glass-panel clip-rounded-lg rounded-lg p-4">
          <h2 className="text-sm font-semibold text-on-surface">{t("orders.detail.payments")}</h2>
          <div className="mt-2 space-y-2">
            {order.payments.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between rounded-lg bg-surface-container-high px-3 py-2"
              >
                <div>
                  <div className="text-sm font-semibold text-expense">
                    -{formatMoney(p.amount, order.currency)}
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

      {order.notes && (
        <section className="glass-panel clip-rounded-lg rounded-lg p-4">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
            {t("orders.detail.notes")}
          </h2>
          <p className="mt-1 text-sm text-on-surface">{order.notes}</p>
        </section>
      )}

      <Dialog open={confirmSend} onOpenChange={setConfirmSend}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>
              {t("orders.confirm.sendTitle", { number: order.number })}
            </DialogTitle>
            <DialogDescription>{t("orders.confirm.sendMessage")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmSend(false)}>
              {t("common.cancel")}
            </Button>
            <Button variant="glow" onClick={() => send.mutate()} disabled={send.isPending}>
              {send.isPending ? t("orders.sending") : t("orders.send")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmReceive} onOpenChange={setConfirmReceive}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>
              {t("orders.confirm.receiveTitle", { number: order.number })}
            </DialogTitle>
            <DialogDescription>{t("orders.confirm.receiveMessage")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmReceive(false)}>
              {t("common.cancel")}
            </Button>
            <Button variant="glow" onClick={() => receive.mutate()} disabled={receive.isPending}>
              {receive.isPending ? t("orders.receiving") : t("orders.receive")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmCancel} onOpenChange={setConfirmCancel}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>
              {t("orders.confirm.cancelTitle", { number: order.number })}
            </DialogTitle>
            <DialogDescription>{t("orders.confirm.cancelMessage")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmCancel(false)}>
              {t("common.cancel")}
            </Button>
            <Button variant="destructive" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
              {cancel.isPending ? t("orders.canceling") : t("orders.cancel")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={payOpen} onOpenChange={setPayOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t("orders.confirm.payTitle")}</DialogTitle>
            <DialogDescription>{t("orders.detail.payHint")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-on-surface">
                {t("orders.detail.payAmount")} ({t("orders.detail.payMax")}{" "}
                {formatMoney(balanceDue, order.currency)})
              </span>
              <NumericInput value={payAmount} onChange={setPayAmount} />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-on-surface">
                {t("orders.detail.payNote")}
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
              {pay.isPending ? t("orders.paying") : t("orders.pay")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}