import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { sileo } from "sileo";
import { Info, PackagePlus, Plus, ShoppingCart, Trash2, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { NumericInput } from "@/components/ui/numeric-input";
import { Segmented } from "@/components/ui/segmented";
import { Switch } from "@/components/ui/switch";
import { api, ApiErrorClass } from "@/lib/api";
import {
  queryKeys,
  useBusiness,
  useBusinessContacts,
  useProductCategories,
  useProducts,
} from "@/hooks/use-queries";
import { formatMoney } from "@/lib/format";
import type { Order, OrderLineDraft, OrderNewProduct } from "@/lib/types";

interface ItemRow {
  kind: "existing" | "new";
  product?: string;
  new_product?: OrderNewProduct;
  description: string;
  quantity: string;
  unit_price: string;
  discount: string;
}

function emptyNewProduct(): OrderNewProduct {
  return {
    name: "",
    sku: "",
    unit: "unidad",
    category: null,
    unit_price: "",
    wholesale_price: null,
    cost_price: null,
    low_stock_threshold: null,
    is_active: true,
  };
}

function emptyItem(): ItemRow {
  return { kind: "existing", description: "", quantity: "1", unit_price: "", discount: "" };
}



/** Prefill del CTA «aprovisionar stock bajo» (llegó vía state del router). */
interface PrefillState {
  prefill?: Array<{ product: string; quantity: string; unit_price: string }>;
}

export default function OrderNewPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();

  const { data: business } = useBusiness();
  const { data: suppliersData } = useBusinessContacts();
  const suppliers = useMemo(
    () => (suppliersData?.results ?? []).filter((c) => c.type !== "cliente" && c.is_active),
    [suppliersData],
  );
  const { data: productsData } = useProducts();
  const catalogue = useMemo(() => productsData?.results ?? [], [productsData]);
  const { data: categoriesData } = useProductCategories();
  const categories = useMemo(() => categoriesData?.results ?? [], [categoriesData]);

  const prefill = useMemo(() => (location.state as PrefillState | null)?.prefill ?? [], [location.state]);

  const [supplierSearch, setSupplierSearch] = useState("");
  const [debouncedSupplierSearch, setDebouncedSupplierSearch] = useState("");
  const [selectedSupplier, setSelectedSupplier] = useState<string>("");
  const [orderDate, setOrderDate] = useState("");
  const [shippingAmount, setShippingAmount] = useState("");
  const [paidAmount, setPaidAmount] = useState("");
  const [notes, setNotes] = useState("");
  const [items, setItems] = useState<ItemRow[]>(() => {
    if (prefill.length === 0) return [emptyItem()];
    return prefill.map((line) => ({
      kind: "existing",
      product: line.product,
      description: "",
      quantity: line.quantity,
      unit_price: line.unit_price,
      discount: "",
    }));
  });

  useEffect(() => {
    const id = setTimeout(() => setDebouncedSupplierSearch(supplierSearch), 300);
    return () => clearTimeout(id);
  }, [supplierSearch]);

  const supplierMatches = useMemo(
    () =>
      suppliers.filter((s) =>
        debouncedSupplierSearch
          ? s.name.toLowerCase().includes(debouncedSupplierSearch.toLowerCase())
          : true
      ),
    [suppliers, debouncedSupplierSearch],
  );

  const updateItem = (idx: number, patch: Partial<ItemRow>) =>
    setItems((rows) => rows.map((row, i) => (i === idx ? { ...row, ...patch } : row)));

  const setNewProductField = (idx: number, patch: Partial<OrderNewProduct>) =>
    updateItem(idx, { new_product: { ...emptyNewProduct(), ...items[idx].new_product, ...patch } });

  const pickLineKind = (idx: number, kind: "existing" | "new") => {
    if (kind === "new") {
      updateItem(idx, { kind, product: undefined, new_product: emptyNewProduct(), description: "", unit_price: "" });
    } else {
      updateItem(idx, { kind, new_product: undefined, description: "", unit_price: "" });
    }
  };

  const pickProduct = (idx: number, productId: string) => {
    const product = catalogue.find((p) => p.id === productId);
    updateItem(idx, {
      product: productId,
      description: product?.name ?? "",
      unit_price: product?.cost_price ?? product?.unit_price ?? "",
    });
  };

  const subtotal = useMemo(
    () =>
      items.reduce((sum, row) => {
        const qty = Number(row.quantity) || 0;
        const price = Number(row.unit_price) || 0;
        const disc = Number(row.discount) || 0;
        return sum + qty * price - disc;
      }, 0),
    [items],
  );
  const shipping = Number(shippingAmount) || 0;
  const total = subtotal + shipping;
  const paid = Number(paidAmount) || 0;
  const walletSaldo = Number(business?.saldo ?? 0);
  const currency = business?.currency ?? "USD";

  const validationError = useMemo(() => {
    if (!selectedSupplier) return t("orders.form.errors.contact");
    if (items.length === 0) return t("orders.form.errors.items");
    if (items.some((r) => r.kind === "existing" && !r.description.trim()))
      return t("orders.form.errors.itemDescription");
    if (items.some((r) => r.kind === "new" && !(r.new_product?.name.trim() ?? "")))
      return t("orders.form.errors.newProductName");
    if (items.some((r) => r.kind === "new" && !(r.new_product?.unit_price ?? "")))
      return t("orders.form.errors.invalidPrice");
    if (items.some((r) => Number(r.unit_price) < 0))
      return t("orders.form.errors.invalidPrice");
    if (items.some((r) => (Number(r.quantity) || 0) <= 0))
      return t("orders.form.errors.invalidQty");
    if (
      items.some((r) => {
        const unit =
          r.kind === "new"
            ? r.new_product?.unit ?? "unidad"
            : catalogue.find((c) => c.id === r.product)?.unit;
        return unit === "unidad" && !/^\d+$/.test(r.quantity.trim());
      })
    )
      return t("inventory.integerRequired");
    if (shipping < 0) return t("orders.form.errors.invalidShipping");
    if (paid < 0) return t("orders.form.errors.invalidPaid");
    if (paid > total) return t("orders.form.errors.paidOverTotal");
    if (paid > 0 && paid > walletSaldo) return t("orders.form.errors.insufficient");
    return null;
  }, [selectedSupplier, items, catalogue, shipping, paid, total, walletSaldo, t]);

  const create = useMutation({
    mutationFn: () => {
      const payload: Record<string, unknown> = {
        contact: selectedSupplier,
        items: items.map((r): OrderLineDraft => {
          const base = {
            description: r.description.trim(),
            quantity: r.quantity,
            ...(r.unit_price !== "" ? { unit_price: r.unit_price } : {}),
            ...(r.discount ? { discount: r.discount } : {}),
          };
          if (r.kind === "new" && r.new_product) {
            return { ...base, new_product: r.new_product };
          }
          return { ...base, product: r.product };
        }),
        ...(orderDate ? { order_date: orderDate } : {}),
        ...(shippingAmount ? { shipping_amount: shippingAmount } : {}),
        ...(paidAmount ? { paid_amount: paidAmount } : {}),
        ...(notes.trim() ? { notes: notes.trim() } : {}),
      };
      return api.post<Order>("/business/orders/", payload);
    },
    onSuccess: (order) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.orders });
      sileo.success({ title: t("orders.created") });
      navigate(`/business/orders/${order.id}`);
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
          <ShoppingCart className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-on-surface">{t("orders.form.title")}</h1>
        </div>
      </div>

      {prefill.length > 0 && (
        <p className="glass-panel clip-rounded-lg flex items-start gap-2 rounded-lg p-3 text-sm text-on-surface-variant">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          {t("orders.form.prefillBanner")}
        </p>
      )}

      <section className="space-y-3">
        <div>
          <span className="mb-1 block text-sm font-medium text-on-surface">
            {t("orders.form.contact")} *
          </span>
          {selectedSupplier ? (
            <div className="glass-panel clip-rounded-lg flex items-center justify-between gap-3 rounded-lg p-3">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10">
                  <Users className="h-4 w-4 text-primary" />
                </div>
                <span className="truncate font-medium text-on-surface">
                  {suppliers.find((s) => s.id === selectedSupplier)?.name ?? selectedSupplier}
                </span>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setSelectedSupplier("")}>
                {t("orders.form.changeSupplier")}
              </Button>
            </div>
          ) : suppliers.length === 0 ? (
            <p className="glass-panel clip-rounded-lg rounded-lg p-4 text-sm text-on-surface-variant">
              {t("orders.form.noSuppliers")}
            </p>
          ) : (
            <div className="space-y-2">
              <Input
                value={supplierSearch}
                onChange={(e) => setSupplierSearch(e.target.value)}
                placeholder={t("orders.form.searchSupplier")}
                inputMode="search"
              />
              <div className="max-h-56 space-y-1 overflow-y-auto">
                {supplierMatches.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => setSelectedSupplier(s.id)}
                    className="flex w-full items-center justify-between gap-3 rounded-lg border border-glass-border bg-glass-surface px-3 py-2 text-left transition-colors hover:border-primary/50"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium text-on-surface">
                        {s.name}
                      </span>
                      <span className="block truncate text-xs text-on-surface-variant">
                        {s.tax_id || t("contacts.noTaxId")}
                      </span>
                    </span>
                    <Badge variant="secondary">
                      {s.type === "ambos" ? t("contacts.types.ambos") : t("contacts.types.proveedor")}
                    </Badge>
                  </button>
                ))}
                {supplierMatches.length === 0 && (
                  <p className="py-2 text-center text-sm text-on-surface-variant">
                    {t("contacts.emptyFiltered")}
                  </p>
                )}
              </div>
            </div>
          )}
        </div>

        <label className="block">
          <span className="mb-1 block text-sm font-medium text-on-surface">
            {t("orders.form.orderDate")}
          </span>
          <Input type="date" value={orderDate} onChange={(e) => setOrderDate(e.target.value)} />
        </label>
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-on-surface">{t("orders.form.items")}</h2>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setItems((rows) => [...rows, emptyItem()])}
            className="gap-1"
          >
            <Plus className="h-4 w-4" /> {t("orders.form.addItem")}
          </Button>
        </div>

        {items.map((row, idx) => (
          <div
            key={idx}
            className="glass-panel clip-rounded-lg space-y-3 rounded-lg p-3"
          >
            <div className="flex items-center justify-between gap-2">
              <Segmented<"existing" | "new">
                size="sm"
                layoutId={`order-line-kind-${idx}`}
                options={[
                  { value: "existing", label: t("orders.form.existingProduct") },
                  { value: "new", label: t("orders.form.newProduct") },
                ]}
                value={row.kind}
                onChange={(kind) => pickLineKind(idx, kind)}
              />
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

            {row.kind === "existing" ? (
              catalogue.length > 0 ? (
                <select
                  value={row.product ?? ""}
                  onChange={(e) => pickProduct(idx, e.target.value)}
                  className="h-11 w-full rounded-xl border border-glass-border bg-glass-surface px-3 text-base text-on-surface shadow-sm outline-none backdrop-blur-md focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 md:text-sm"
                >
                  <option value="">{t("orders.form.fromCatalogue")}</option>
                  {catalogue.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} · {t("inventory.stock")}: {p.stock_quantity}
                    </option>
                  ))}
                </select>
              ) : (
                <p className="text-sm text-on-surface-variant">{t("inventory.empty")}</p>
              )
            ) : (
              <div className="space-y-3 border-t border-glass-border pt-3">
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="block">
                    <span className="mb-1 block text-sm font-medium text-on-surface">
                      {t("orders.form.newProductName")} *
                    </span>
                    <Input
                      value={row.new_product?.name ?? ""}
                      onChange={(e) => setNewProductField(idx, { name: e.target.value })}
                      placeholder={t("inventory.namePlaceholder")}
                    />
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-sm font-medium text-on-surface">
                      {t("inventory.sku")}
                    </span>
                    <Input
                      value={row.new_product?.sku ?? ""}
                      onChange={(e) => setNewProductField(idx, { sku: e.target.value })}
                      placeholder={t("inventory.skuPlaceholder")}
                    />
                  </label>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="block">
                    <span className="mb-1 block text-sm font-medium text-on-surface">
                      {t("inventory.unit")}
                    </span>
                    <Segmented<"unidad" | "kg">
                      size="sm"
                      options={[
                        { value: "unidad", label: t("inventory.units.unidad") },
                        { value: "kg", label: t("inventory.units.kg") },
                      ]}
                      value={row.new_product?.unit ?? "unidad"}
                      onChange={(unit) => setNewProductField(idx, { unit })}
                      layoutId={`order-new-unit-${idx}`}
                    />
                  </div>
                  <label className="block">
                    <span className="mb-1 block text-sm font-medium text-on-surface">
                      {t("inventory.category")}
                    </span>
                    <select
                      value={row.new_product?.category ?? ""}
                      onChange={(e) =>
                        setNewProductField(idx, { category: e.target.value || null })
                      }
                      className="h-11 w-full rounded-xl border border-glass-border bg-glass-surface px-3 text-base text-on-surface shadow-sm outline-none backdrop-blur-md focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 md:text-sm"
                    >
                      <option value="">{t("inventory.noCategory")}</option>
                      {categories.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                  <label className="block">
                    <span className="mb-1 block text-sm font-medium text-on-surface">
                      {t("inventory.unitPrice")} *
                    </span>
                    <NumericInput
                      value={row.new_product?.unit_price ?? ""}
                      onChange={(v) => setNewProductField(idx, { unit_price: v })}
                    />
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-sm font-medium text-on-surface">
                      {t("inventory.wholesalePrice")}
                    </span>
                    <NumericInput
                      value={row.new_product?.wholesale_price ?? ""}
                      onChange={(v) => setNewProductField(idx, { wholesale_price: v || null })}
                    />
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-sm font-medium text-on-surface">
                      {t("inventory.costPrice")}
                    </span>
                    <NumericInput
                      value={row.new_product?.cost_price ?? ""}
                      onChange={(v) => setNewProductField(idx, { cost_price: v || null })}
                    />
                  </label>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="block">
                    <span className="mb-1 block text-sm font-medium text-on-surface">
                      {t("inventory.threshold")}
                    </span>
                    <NumericInput
                      mode={row.new_product?.unit === "unidad" ? "integer" : "decimal"}
                      value={row.new_product?.low_stock_threshold ?? ""}
                      onChange={(v) =>
                        setNewProductField(idx, { low_stock_threshold: v || null })
                      }
                    />
                  </label>
                  <label className="flex items-center justify-between gap-3 rounded-xl bg-surface-container-high px-3 py-2.5">
                    <div>
                      <div className="text-sm font-medium text-on-surface">
                        {t("inventory.active")}
                      </div>
                      <div className="text-xs text-on-surface-variant">
                        {t("inventory.inactive")}
                      </div>
                    </div>
                    <Switch
                      checked={row.new_product?.is_active ?? true}
                      onCheckedChange={(checked) => setNewProductField(idx, { is_active: checked })}
                    />
                  </label>
                </div>
                <p className="flex items-start gap-1.5 text-xs text-on-surface-variant">
                  <PackagePlus className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  {t("orders.form.newProductHint")}
                </p>
              </div>
            )}

            <div className="grid grid-cols-12 items-center gap-2">
              <NumericInput
                className="col-span-3"
                mode={
                  row.kind === "new"
                    ? row.new_product?.unit === "unidad"
                      ? "integer"
                      : "decimal"
                    : row.product &&
                        catalogue.find((c) => c.id === row.product)?.unit === "unidad"
                      ? "integer"
                      : "decimal"
                }
                placeholder={t("orders.form.itemQty")}
                value={row.quantity}
                onChange={(v) => updateItem(idx, { quantity: v })}
              />
              <NumericInput
                className="col-span-4"
                placeholder={t("orders.form.itemPrice")}
                value={row.unit_price}
                onChange={(v) => updateItem(idx, { unit_price: v })}
              />
              <NumericInput
                className="col-span-2"
                placeholder={t("orders.form.itemDiscount")}
                value={row.discount}
                onChange={(v) => updateItem(idx, { discount: v })}
              />
              <div className="col-span-3 flex items-center justify-end">
                <span className="text-sm font-medium text-on-surface">
                  {formatMoney(
                    (Number(row.quantity) || 0) * (Number(row.unit_price) || 0) -
                      (Number(row.discount) || 0),
                    currency
                  )}
                </span>
              </div>
            </div>
          </div>
        ))}
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-on-surface">
            {t("orders.form.shippingAmount")}
          </span>
          <NumericInput value={shippingAmount} onChange={setShippingAmount} />
          <span className="mt-1 block text-xs text-on-surface-variant">
            {t("orders.form.shippingHint")}
          </span>
        </label>
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-on-surface">
            {t("orders.form.paidAmount")}
          </span>
          <NumericInput value={paidAmount} onChange={setPaidAmount} />
          <span className="mt-1 block text-xs text-on-surface-variant">
            {t("orders.form.paidHint")}
          </span>
          {Number(paidAmount) > 0 && (
            <span className="mt-1 block text-xs text-warning-text">
              {t("orders.form.payable")}: {formatMoney(walletSaldo, currency)}
            </span>
          )}
        </label>
      </section>

      <section className="glass-panel clip-rounded-lg rounded-lg p-4">
        <div className="flex justify-between text-sm text-on-surface-variant">
          <span>{t("orders.detail.subtotal")}</span>
          <span>{formatMoney(subtotal, currency)}</span>
        </div>
        <div className="flex justify-between text-sm text-on-surface-variant">
          <span>{t("orders.detail.shipping")}</span>
          <span>{formatMoney(shipping, currency)}</span>
        </div>
        <div className="mt-1 flex justify-between border-t border-glass-border pt-2 text-base font-semibold text-on-surface">
          <span>{t("orders.detail.total")}</span>
          <span>{formatMoney(total, currency)}</span>
        </div>
      </section>

      <label className="block">
        <span className="mb-1 block text-sm font-medium text-on-surface">
          {t("orders.form.notes")}
        </span>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          placeholder={t("orders.form.notesPlaceholder")}
          className="h-auto w-full rounded-xl border border-glass-border bg-glass-surface px-3 py-2.5 text-base text-on-surface shadow-sm outline-none backdrop-blur-md focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 md:text-sm"
        />
      </label>

      {validationError && (
        <p className="text-sm text-destructive">{validationError}</p>
      )}

      <div className="flex gap-2">
        <Button variant="ghost" onClick={() => navigate("/business/orders")} disabled={create.isPending}>
          {t("common.cancel")}
        </Button>
        <Button
          variant="glow"
          onClick={() => create.mutate()}
          disabled={Boolean(validationError) || create.isPending}
          className="gap-1"
        >
          {create.isPending ? t("orders.form.creating") : t("orders.form.create")}
        </Button>
      </div>
    </div>
  );
}