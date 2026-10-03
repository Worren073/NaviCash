import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, ReceiptText, Trash2, UserPlus } from "lucide-react";
import { sileo } from "sileo";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiErrorClass } from "@/lib/api";
import { queryKeys, useBusinessContacts } from "@/hooks/use-queries";
import { formatMoney } from "@/lib/format";
import type { Invoice } from "@/lib/types";

interface ItemRow {
  description: string;
  quantity: string;
  unit_price: string;
  discount: string;
}

function emptyItem(): ItemRow {
  return { description: "", quantity: "1", unit_price: "", discount: "" };
}

function lineTotal(row: ItemRow): number {
  const qty = Number(row.quantity) || 0;
  const price = Number(row.unit_price) || 0;
  const disc = Number(row.discount) || 0;
  return qty * price - disc;
}

export default function InvoiceNewPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: contactsData } = useBusinessContacts();
  const customers = useMemo(
    () => (contactsData?.results ?? []).filter((c) => c.type !== "proveedor" && c.is_active),
    [contactsData]
  );

  const [contact, setContact] = useState("");
  const [issueDate, setIssueDate] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [taxAmount, setTaxAmount] = useState("");
  const [paidAmount, setPaidAmount] = useState("");
  const [notes, setNotes] = useState("");
  const [items, setItems] = useState<ItemRow[]>([emptyItem()]);

  const subtotal = useMemo(
    () => items.reduce((sum, row) => sum + lineTotal(row), 0),
    [items]
  );
  const tax = Number(taxAmount) || 0;
  const total = subtotal + tax;
  const paid = Number(paidAmount) || 0;

  const updateItem = (idx: number, patch: Partial<ItemRow>) =>
    setItems((rows) => rows.map((row, i) => (i === idx ? { ...row, ...patch } : row)));

  const setItem = (idx: number, key: keyof ItemRow, value: string) =>
    updateItem(idx, { [key]: value });

  const validationError = useMemo(() => {
    if (!contact) return t("invoices.form.errors.contact");
    if (items.length === 0 || items.some((r) => !r.description.trim()))
      return t("invoices.form.errors.itemDescription");
    if (items.some((r) => (Number(r.quantity) || 0) <= 0))
      return t("invoices.form.errors.invalidQty");
    if (items.some((r) => ((Number(r.unit_price) || 0)) < 0))
      return t("invoices.form.errors.invalidPrice");
    if (tax < 0) return t("invoices.form.errors.invalidTax");
    if (paid < 0) return t("invoices.form.errors.invalidPaid");
    if (paid > total) return t("invoices.form.errors.paidOverTotal");
    if (dueDate && issueDate && dueDate < issueDate)
      return t("invoices.form.errors.invalidDate");
    return null;
  }, [contact, items, tax, paid, total, dueDate, issueDate, t]);

  const create = useMutation({
    mutationFn: () => {
      const payload: Record<string, unknown> = {
        contact,
        items: items.map((r) => ({
          description: r.description.trim(),
          quantity: r.quantity,
          unit_price: r.unit_price,
          ...(r.discount ? { discount: r.discount } : {}),
        })),
        ...(issueDate ? { issue_date: issueDate } : {}),
        ...(dueDate ? { due_date: dueDate } : {}),
        ...(taxAmount ? { tax_amount: taxAmount } : {}),
        ...(paidAmount ? { paid_amount: paidAmount } : {}),
        ...(notes.trim() ? { notes: notes.trim() } : {}),
      };
      return api.post<Invoice>("/business/invoices/", payload);
    },
    onSuccess: (inv) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.invoices });
      sileo.success({ title: t("invoices.created") });
      navigate(`/business/invoices/${inv.id}`);
    },
    onError: (err) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("errors.generic");
      sileo.error({ title: msg });
    },
  });

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
          <ReceiptText className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-on-surface">{t("invoices.form.title")}</h1>
        </div>
      </div>

      <section className="space-y-4">
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-on-surface">
            {t("invoices.form.contact")}
          </span>
          {customers.length === 0 ? (
            <Link to="/business/contacts" className="text-sm text-primary hover:underline">
              {t("invoices.form.newContact")} <UserPlus className="inline h-4 w-4" />
            </Link>
          ) : (
            <select
              value={contact}
              onChange={(e) => setContact(e.target.value)}
              className="h-11 w-full rounded-xl border border-glass-border bg-glass-surface px-3 text-base text-on-surface shadow-sm outline-none backdrop-blur-md focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 md:text-sm"
            >
              <option value="">{t("invoices.form.contactPlaceholder")}</option>
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          )}
        </label>

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-on-surface">
              {t("invoices.form.issueDate")}
            </span>
            <Input type="date" value={issueDate} onChange={(e) => setIssueDate(e.target.value)} />
          </label>

          <label className="block">
            <span className="mb-1 block text-sm font-medium text-on-surface">
              {t("invoices.form.dueDate")}
            </span>
            <Input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
            <span className="mt-1 block text-xs text-on-surface-variant">
              {t("invoices.form.dueAuto")}
            </span>
          </label>
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-on-surface">{t("invoices.form.items")}</h2>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setItems((rows) => [...rows, emptyItem()])}
            className="gap-1"
          >
            <Plus className="h-4 w-4" /> {t("invoices.form.addItem")}
          </Button>
        </div>

        {items.map((row, idx) => (
          <div
            key={idx}
            className="glass-panel clip-rounded-lg grid grid-cols-12 items-center gap-2 rounded-lg p-3"
          >
            <Input
              className="col-span-12 sm:col-span-4"
              placeholder={t("invoices.form.itemDescription")}
              value={row.description}
              onChange={(e) => setItem(idx, "description", e.target.value)}
            />
            <Input
              className="col-span-4 sm:col-span-2"
              type="number"
              inputMode="decimal"
              placeholder={t("invoices.form.itemQty")}
              value={row.quantity}
              onChange={(e) => setItem(idx, "quantity", e.target.value)}
            />
            <Input
              className="col-span-4 sm:col-span-3"
              type="number"
              inputMode="decimal"
              placeholder={t("invoices.form.itemPrice")}
              value={row.unit_price}
              onChange={(e) => setItem(idx, "unit_price", e.target.value)}
            />
            <div className="col-span-2 flex items-center justify-end gap-2 sm:col-span-1">
              <Input
                className="w-full"
                type="number"
                inputMode="decimal"
                placeholder={t("invoices.form.itemDiscount")}
                value={row.discount}
                onChange={(e) => setItem(idx, "discount", e.target.value)}
              />
            </div>
            <div className="col-span-2 flex items-center justify-end gap-2 sm:col-span-2">
              <span className="text-sm font-medium text-on-surface">
                {formatMoney(lineTotal(row))}
              </span>
              {items.length > 1 && (
                <button
                  type="button"
                  onClick={() => setItems((rows) => rows.filter((_, i) => i !== idx))}
                  className="text-on-surface-variant transition-colors hover:text-destructive"
                  aria-label={t("common.delete")}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </div>
          </div>
        ))}
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-on-surface">
            {t("invoices.form.taxAmount")}
          </span>
          <Input
            type="number"
            inputMode="decimal"
            value={taxAmount}
            onChange={(e) => setTaxAmount(e.target.value)}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-on-surface">
            {t("invoices.form.paidAmount")}
          </span>
          <Input
            type="number"
            inputMode="decimal"
            value={paidAmount}
            onChange={(e) => setPaidAmount(e.target.value)}
          />
          <span className="mt-1 block text-xs text-on-surface-variant">
            {t("invoices.form.paidHint")}
          </span>
        </label>
      </section>

      <section className="glass-panel clip-rounded-lg rounded-lg p-4">
        <div className="flex justify-between text-sm text-on-surface-variant">
          <span>{t("invoices.detail.subtotal")}</span>
          <span>{formatMoney(subtotal)}</span>
        </div>
        <div className="flex justify-between text-sm text-on-surface-variant">
          <span>{t("invoices.detail.tax")}</span>
          <span>{formatMoney(tax)}</span>
        </div>
        <div className="mt-1 flex justify-between border-t border-glass-border pt-2 text-base font-semibold text-on-surface">
          <span>{t("invoices.detail.total")}</span>
          <span>{formatMoney(total)}</span>
        </div>
      </section>

      <label className="block">
        <span className="mb-1 block text-sm font-medium text-on-surface">
          {t("invoices.form.notes")}
        </span>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          placeholder={t("invoices.form.notesPlaceholder")}
          className="h-auto w-full rounded-xl border border-glass-border bg-glass-surface px-3 py-2.5 text-base text-on-surface shadow-sm outline-none backdrop-blur-md focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 md:text-sm"
        />
      </label>

      {validationError && (
        <p className="text-sm text-destructive">{validationError}</p>
      )}

      <div className="flex gap-2">
        <Button
          variant="ghost"
          onClick={() => navigate("/business/invoices")}
          disabled={create.isPending}
        >
          {t("common.cancel")}
        </Button>
        <Button
          variant="glow"
          onClick={() => create.mutate()}
          disabled={Boolean(validationError) || create.isPending}
          className="gap-1"
        >
          {create.isPending ? t("invoices.form.creating") : t("invoices.form.create")}
        </Button>
      </div>
    </div>
  );
}