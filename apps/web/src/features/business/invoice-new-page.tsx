import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, ReceiptText, Trash2, UserPlus, Users } from "lucide-react";
import { sileo } from "sileo";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Segmented } from "@/components/ui/segmented";
import { api, ApiErrorClass } from "@/lib/api";
import { queryKeys, useBusinessContacts, useProducts } from "@/hooks/use-queries";
import { formatMoney } from "@/lib/format";
import { TAX_ID_TYPES, formatTaxId, isValidTaxId, taxIdSearchTerm, type TaxIdType } from "@/lib/tax-id";
import type { BusinessContact, Invoice } from "@/lib/types";
import {
  ContactForm,
  emptyContactForm,
  type ContactFormValue,
} from "./contact-form";

interface ItemRow {
  product?: string;
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

  const [docType, setDocType] = useState<TaxIdType>("V");
  const [contactSearch, setContactSearch] = useState("");
  const [debouncedContactSearch, setDebouncedContactSearch] = useState("");
  const [selectedContact, setSelectedContact] = useState<BusinessContact | null>(null);
  const [affiliateOpen, setAffiliateOpen] = useState(false);
  const [affiliateForm, setAffiliateForm] = useState<ContactFormValue>(emptyContactForm());

  useEffect(() => {
    const id = setTimeout(() => setDebouncedContactSearch(contactSearch), 300);
    return () => clearTimeout(id);
  }, [contactSearch]);

  const { term } = taxIdSearchTerm(debouncedContactSearch, docType);
  const { data: contactsData } = useBusinessContacts(term || undefined);
  const matches = useMemo(
    () => (contactsData?.results ?? []).filter((c) => c.type !== "proveedor" && c.is_active),
    [contactsData],
  );
  const { data: productsData } = useProducts();
  const catalogue = useMemo(() => productsData?.results ?? [], [productsData]);

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

  const pickProduct = (idx: number, productId: string) => {
    const product = catalogue.find((p) => p.id === productId);
    if (!product) return;
    const isMayorista = selectedContact?.customer_type === "mayorista";
    const price =
      isMayorista && product.wholesale_price
        ? product.wholesale_price
        : product.unit_price;
    updateItem(idx, {
      product: product.id,
      description: product.name,
      unit_price: price,
    });
  };

  const validationError = useMemo(() => {
    if (!selectedContact) return t("invoices.form.errors.contact");
    if (items.length === 0 || items.some((r) => !r.description.trim()))
      return t("invoices.form.errors.itemDescription");
    if (items.some((r) => (Number(r.quantity) || 0) <= 0))
      return t("invoices.form.errors.invalidQty");
    // Producto «por unidad»: la cantidad de la línea debe ser entera.
    if (
      items.some((r) => {
        const p = r.product ? catalogue.find((c) => c.id === r.product) : undefined;
        return (
          p?.unit === "unidad" && r.quantity !== "" && !Number.isInteger(Number(r.quantity))
        );
      })
    )
      return t("inventory.integerRequired");
    if (items.some((r) => ((Number(r.unit_price) || 0)) < 0))
      return t("invoices.form.errors.invalidPrice");
    if (tax < 0) return t("invoices.form.errors.invalidTax");
    if (paid < 0) return t("invoices.form.errors.invalidPaid");
    if (paid > total) return t("invoices.form.errors.paidOverTotal");
    if (dueDate && issueDate && dueDate < issueDate)
      return t("invoices.form.errors.invalidDate");
    return null;
  }, [selectedContact, items, catalogue, tax, paid, total, dueDate, issueDate, t]);

  const openAffiliate = () => {
    const form = emptyContactForm();
    form.tax_id = formatTaxId(docType, taxIdSearchTerm(contactSearch, docType).number);
    setAffiliateForm(form);
    setAffiliateOpen(true);
  };

  const affiliate = useMutation({
    mutationFn: () =>
      api.post<BusinessContact>("/business/contacts/", {
        ...affiliateForm,
        type: "cliente",
        credit_limit: affiliateForm.credit_limit === "" ? null : affiliateForm.credit_limit,
      }),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.businessContacts });
      setSelectedContact(created);
      setAffiliateOpen(false);
      setContactSearch("");
      sileo.success({ title: t("contacts.created") });
    },
    onError: (err) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("errors.generic");
      sileo.error({ title: msg });
    },
  });

  const create = useMutation({
    mutationFn: () => {
      const payload: Record<string, unknown> = {
        contact: selectedContact?.id,
        items: items.map((r) => ({
          description: r.description.trim(),
          quantity: r.quantity,
          unit_price: r.unit_price,
          ...(r.product ? { product: r.product } : {}),
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
        <div>
          <span className="mb-1 block text-sm font-medium text-on-surface">
            {t("invoices.form.contact")} *
          </span>
          {selectedContact ? (
            <div className="glass-panel clip-rounded-lg flex items-center justify-between gap-3 rounded-lg p-3">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10">
                  <Users className="h-4 w-4 text-primary" />
                </div>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate font-medium text-on-surface">
                      {selectedContact.name}
                    </span>
                    {selectedContact.customer_type && (
                      <Badge variant="outline">
                        {t(`contacts.customerTypes.${selectedContact.customer_type}`)}
                      </Badge>
                    )}
                  </div>
                  <div className="truncate text-xs text-on-surface-variant">
                    {selectedContact.tax_id || t("contacts.noTaxId")}
                  </div>
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSelectedContact(null)}
              >
                {t("invoices.form.changeClient")}
              </Button>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <div className="w-32 shrink-0">
                  <Segmented<TaxIdType>
                    options={TAX_ID_TYPES.map((value) => ({ value, label: value }))}
                    value={docType}
                    onChange={(next) => {
                      setDocType(next);
                      const { number } = taxIdSearchTerm(contactSearch, next);
                      setContactSearch(number);
                    }}
                    layoutId="invoice-doc-type"
                    size="sm"
                  />
                </div>
                <Input
                  value={contactSearch}
                  onChange={(e) => setContactSearch(e.target.value)}
                  placeholder={t("invoices.form.searchClient")}
                  inputMode="search"
                  className="flex-1"
                />
              </div>

              {matches.length > 0 && (
                <div className="max-h-56 space-y-1 overflow-y-auto">
                  {matches.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => setSelectedContact(c)}
                      className="flex w-full items-center justify-between gap-3 rounded-lg border border-glass-border bg-glass-surface px-3 py-2 text-left transition-colors hover:border-primary/50"
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium text-on-surface">
                          {c.name}
                        </span>
                        <span className="block truncate text-xs text-on-surface-variant">
                          {c.tax_id || t("contacts.noTaxId")}
                        </span>
                      </span>
                      {c.customer_type && (
                        <Badge variant="secondary">
                          {t(`contacts.customerTypes.${c.customer_type}`)}
                        </Badge>
                      )}
                    </button>
                  ))}
                </div>
              )}

              {term && matches.length === 0 && (
                <Button
                  variant="ghost"
                  onClick={openAffiliate}
                  className="w-full justify-center gap-1 border border-dashed border-glass-border"
                >
                  <UserPlus className="h-4 w-4" />
                  {t("invoices.form.affiliateClient")}
                  {term && taxIdSearchTerm(contactSearch, docType).number
                    ? ` ${formatTaxId(docType, taxIdSearchTerm(contactSearch, docType).number)}`
                    : ""}
                </Button>
              )}
            </div>
          )}
        </div>

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
            {catalogue.length > 0 && (
              <select
                value={row.product ?? ""}
                onChange={(e) => pickProduct(idx, e.target.value)}
                className="col-span-12 h-11 w-full rounded-xl border border-glass-border bg-glass-surface px-3 text-base text-on-surface shadow-sm outline-none backdrop-blur-md focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 md:text-sm"
              >
                <option value="">{t("invoices.form.fromCatalogue")}</option>
                {catalogue.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} · {t("inventory.stock")}: {p.stock_quantity}
                  </option>
                ))}
              </select>
            )}
            <Input
              className="col-span-12 sm:col-span-4"
              placeholder={t("invoices.form.itemDescription")}
              value={row.description}
              onChange={(e) => setItem(idx, "description", e.target.value)}
            />
            <Input
              className="col-span-4 sm:col-span-2"
              type="number"
              inputMode={
                row.product &&
                catalogue.find((c) => c.id === row.product)?.unit === "unidad"
                  ? "numeric"
                  : "decimal"
              }
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

      <Dialog open={affiliateOpen} onOpenChange={setAffiliateOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>{t("invoices.form.affiliateTitle")}</DialogTitle>
            <DialogDescription>{t("invoices.form.affiliateHint")}</DialogDescription>
          </DialogHeader>
          <ContactForm
            value={affiliateForm}
            onChange={setAffiliateForm}
            fixedTaxIdType={docType}
          />
          <DialogFooter>
            <Button
              variant="ghost"
              onClick={() => setAffiliateOpen(false)}
              disabled={affiliate.isPending}
            >
              {t("common.cancel")}
            </Button>
            <Button
              variant="glow"
              onClick={() => affiliate.mutate()}
              disabled={
                !affiliateForm.name.trim() ||
                Boolean(affiliateForm.tax_id && !isValidTaxId(affiliateForm.tax_id)) ||
                affiliate.isPending
              }
            >
              {affiliate.isPending ? t("common.loading") : t("invoices.form.affiliateSave")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}