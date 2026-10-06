import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { sileo } from "sileo";

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
import { Segmented } from "@/components/ui/segmented";
import { Switch } from "@/components/ui/switch";
import { api, ApiErrorClass } from "@/lib/api";
import { queryKeys, useProductCategories } from "@/hooks/use-queries";
import type { Product } from "@/lib/types";

export function ProductFormDialog({
  product,
  open,
  onOpenChange,
}: {
  product: Product | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: categoriesData } = useProductCategories();
  const categories = useMemo(() => categoriesData?.results ?? [], [categoriesData]);

  const [name, setName] = useState("");
  const [sku, setSku] = useState("");
  const [unit, setUnit] = useState<"unidad" | "kg">("unidad");
  const [category, setCategory] = useState("");
  const [unitPrice, setUnitPrice] = useState("");
  const [wholesalePrice, setWholesalePrice] = useState("");
  const [costPrice, setCostPrice] = useState("");
  const [threshold, setThreshold] = useState("");
  const [initialStock, setInitialStock] = useState("");
  const [isActive, setIsActive] = useState(true);

  useEffect(() => {
    if (open) {
      setName(product?.name ?? "");
      setSku(product?.sku ?? "");
      setUnit(product?.unit === "kg" ? "kg" : "unidad");
      setCategory(product?.category ?? "");
      setUnitPrice(product?.unit_price ?? "");
      setWholesalePrice(product?.wholesale_price ?? "");
      setCostPrice(product?.cost_price ?? "");
      setThreshold(product?.low_stock_threshold ?? "");
      setInitialStock("");
      setIsActive(product?.is_active ?? true);
    }
  }, [open, product]);

  const numberLtZero = (...vals: Array<string | null>) =>
    vals.some((v) => v != null && v !== "" && (Number(v) < 0 || !Number.isFinite(Number(v))));

  const nonInteger = (v: string) => v !== "" && !Number.isInteger(Number(v));

  const validationError = useMemo(() => {
    if (!name.trim()) return t("inventory.nameRequired");
    if (numberLtZero(unitPrice, wholesalePrice, costPrice, threshold, initialStock))
      return t("inventory.nonNegative");
    // Con la unidad «Unidad» las cantidades van en enteros (sin decimales).
    if (unit === "unidad" && (nonInteger(initialStock) || nonInteger(threshold)))
      return t("inventory.integerRequired");
    return null;
  }, [name, unit, unitPrice, wholesalePrice, costPrice, threshold, initialStock, t]);

  const mutation = useMutation({
    mutationFn: () => {
      const base = {
        name: name.trim(),
        sku: sku.trim(),
        unit,
        category: category || null,
        unit_price: unitPrice,
        wholesale_price: wholesalePrice || null,
        cost_price: costPrice,
        low_stock_threshold: threshold || null,
        is_active: isActive,
      };
      if (product) {
        return api.patch<Product>(`/business/products/${product.id}/`, base);
      }
      return api.post<Product>("/business/products/", {
        ...base,
        ...(initialStock ? { stock_quantity: initialStock } : {}),
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.products });
      onOpenChange(false);
      sileo.success({ title: product ? t("inventory.updated") : t("inventory.created") });
    },
    onError: (err) => {
      const msg =
        err instanceof ApiErrorClass
          ? err.message
          : product
            ? t("inventory.updateError")
            : t("inventory.createError");
      sileo.error({ title: msg });
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            {product ? t("inventory.editTitle") : t("inventory.createTitle")}
          </DialogTitle>
          <DialogDescription>
            {product ? "" : t("inventory.initialStockHint")}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-on-surface">
              {t("inventory.name")} *
            </span>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("inventory.namePlaceholder")}
            />
          </label>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-on-surface">
                {t("inventory.sku")}
              </span>
              <Input
                value={sku}
                onChange={(e) => setSku(e.target.value)}
                placeholder={t("inventory.skuPlaceholder")}
              />
            </label>
            <div className="block">
              <span className="mb-1 block text-sm font-medium text-on-surface">
                {t("inventory.unit")}
              </span>
              <Segmented<"unidad" | "kg">
                options={[
                  { value: "unidad", label: t("inventory.units.unidad") },
                  { value: "kg", label: t("inventory.units.kg") },
                ]}
                value={unit}
                onChange={setUnit}
                layoutId="product-unit-segmented"
              />
            </div>
          </div>

          <label className="block">
            <span className="mb-1 block text-sm font-medium text-on-surface">
              {t("inventory.category")}
            </span>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
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

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-on-surface">
                {t("inventory.unitPrice")} *
              </span>
              <NumericInput
                value={unitPrice}
                onChange={setUnitPrice}
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-on-surface">
                {t("inventory.wholesalePrice")}
              </span>
              <NumericInput
                value={wholesalePrice}
                onChange={setWholesalePrice}
              />
            </label>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-on-surface">
                {t("inventory.costPrice")}
              </span>
              <NumericInput
                value={costPrice}
                onChange={setCostPrice}
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-on-surface">
                {t("inventory.threshold")}
              </span>
              <NumericInput
                mode={unit === "unidad" ? "integer" : "decimal"}
                value={threshold}
                onChange={setThreshold}
              />
              <span className="mt-1 block text-xs text-on-surface-variant">
                {t("inventory.thresholdHint")}
              </span>
            </label>
          </div>

          {!product && (
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-on-surface">
                {t("inventory.initialStock")}
              </span>
              <NumericInput
                mode={unit === "unidad" ? "integer" : "decimal"}
                value={initialStock}
                onChange={setInitialStock}
              />
            </label>
          )}

          <label className="flex items-center justify-between gap-3 rounded-xl bg-surface-container-high px-3 py-2.5">
            <div>
              <div className="text-sm font-medium text-on-surface">{t("inventory.active")}</div>
              <div className="text-xs text-on-surface-variant">{t("inventory.inactive")}</div>
            </div>
            <Switch checked={isActive} onCheckedChange={setIsActive} />
          </label>

          {validationError && <p className="text-sm text-destructive">{validationError}</p>}
        </div>
        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={mutation.isPending}
          >
            {t("common.cancel")}
          </Button>
          <Button
            variant="glow"
            onClick={() => mutation.mutate()}
            disabled={Boolean(validationError) || mutation.isPending}
          >
            {mutation.isPending ? t("common.loading") : t("common.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}