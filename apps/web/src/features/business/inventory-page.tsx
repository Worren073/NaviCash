import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { sileo } from "sileo";
import { FolderClosed, Package, Pencil, Plus, Scale, Search, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ConfirmDeleteDialog } from "@/components/ui/confirm-delete-dialog";
import { api, ApiErrorClass } from "@/lib/api";
import {
  queryKeys,
  useProductCategories,
  useProducts,
} from "@/hooks/use-queries";
import { formatMoney } from "@/lib/format";
import type { Product } from "@/lib/types";
import { ProductFormDialog } from "./product-form-dialog";
import { StockAdjustDialog } from "./stock-adjust-dialog";

function CategoryManagerDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data } = useProductCategories();
  const categories = useMemo(() => data?.results ?? [], [data]);
  const [name, setName] = useState("");

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.productCategories });

  const crate = useMutation({
    mutationFn: () => api.post("/business/product-categories/", { name: name.trim() }),
    onSuccess: () => {
      setName("");
      void refresh();
      sileo.success({ title: t("inventory.categoryCreated") });
    },
    onError: (err) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("errors.generic");
      sileo.error({ title: msg });
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/business/product-categories/${id}/`),
    onSuccess: () => {
      void refresh();
      sileo.success({ title: t("inventory.categoryDeleted") });
    },
    onError: (err) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("errors.generic");
      sileo.error({ title: msg });
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{t("inventory.categoriesTitle")}</DialogTitle>
          <DialogDescription />
        </DialogHeader>
        <div className="space-y-4">
          <div className="flex gap-2">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("inventory.categoryNamePlaceholder")}
              onKeyDown={(e) => {
                if (e.key === "Enter" && name.trim()) crate.mutate();
              }}
            />
            <Button
              variant="glow"
              onClick={() => crate.mutate()}
              disabled={!name.trim() || crate.isPending}
              className="shrink-0"
            >
              <Plus className="h-4 w-4" />
            </Button>
          </div>
          {crate.isError && (
            <p className="text-sm text-destructive">
              {crate.error instanceof ApiErrorClass
                ? crate.error.message
                : t("inventory.categoryErrorDuplicate")}
            </p>
          )}
          {categories.length === 0 ? (
            <p className="text-sm text-on-surface-variant">{t("inventory.noCategories")}</p>
          ) : (
            <div className="space-y-2">
              {categories.map((cat) => (
                <div
                  key={cat.id}
                  className="flex items-center justify-between gap-2 rounded-lg bg-surface-container-high px-3 py-2"
                >
                  <span className="text-sm font-medium text-on-surface">{cat.name}</span>
                  <button
                    type="button"
                    onClick={() => remove.mutate(cat.id)}
                    disabled={remove.isPending}
                    className="text-on-surface-variant transition-colors hover:text-destructive"
                    aria-label={t("common.delete")}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.close")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ProductCard({
  product,
  categoryName,
  onEdit,
  onAdjust,
  onDelete,
}: {
  product: Product;
  categoryName?: string;
  onEdit: () => void;
  onAdjust: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="glass-panel clip-rounded-lg flex items-center justify-between gap-3 rounded-lg p-4">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
            <Package className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="truncate text-sm font-semibold text-on-surface">
                {product.name}
              </span>
              {product.is_low_stock && (
                <Badge variant="warning">{t("inventory.lowStock")}</Badge>
              )}
              {!product.is_active && (
                <Badge variant="secondary">{t("inventory.inactive")}</Badge>
              )}
            </div>
            <div className="truncate text-xs text-on-surface-variant">
              {[product.sku, categoryName].filter(Boolean).join(" · ") || "—"}
            </div>
          </div>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <div className="text-right">
          <div className="text-sm font-semibold text-on-surface">{formatMoney(product.unit_price)}</div>
          <div className="text-xs text-on-surface-variant">
            {product.stock_quantity} {product.unit ? product.unit : ""}
          </div>
        </div>
        <div className="flex gap-1">
          <Button variant="ghost" size="sm" onClick={onAdjust} aria-label={t("inventory.adjust")}>
            <Scale className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" onClick={onEdit} aria-label={t("common.edit")}>
            <Pencil className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" onClick={onDelete} aria-label={t("common.delete")}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function InventoryPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const { data: categoriesData } = useProductCategories();
  const categories = useMemo(() => categoriesData?.results ?? [], [categoriesData]);

  const { data, isLoading, isError } = useProducts(
    debouncedSearch || undefined,
    categoryFilter || undefined
  );
  const products = useMemo(() => data?.results ?? [], [data]);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Product | null>(null);
  const [adjusting, setAdjusting] = useState<Product | null>(null);
  const [deleting, setDeleting] = useState<Product | null>(null);
  const [categoriesOpen, setCategoriesOpen] = useState(false);

  useEffect(() => {
    const id = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(id);
  }, [search]);

  const refreshProductData = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.products }),
      queryClient.invalidateQueries({ queryKey: queryKeys.notifications }),
    ]);

  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/business/products/${id}/`),
    onSuccess: async () => {
      setDeleting(null);
      await refreshProductData();
      sileo.success({ title: t("inventory.deleted") });
    },
    onError: (err) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("errors.generic");
      sileo.error({ title: msg });
    },
  });

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
            <Package className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-on-surface">{t("inventory.title")}</h1>
            <p className="text-sm text-on-surface-variant">{t("inventory.subtitle")}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" className="gap-1" onClick={() => setCategoriesOpen(true)}>
            <FolderClosed className="h-4 w-4" /> {t("inventory.categoriesTitle")}
          </Button>
          <Button
            variant="glow"
            className="gap-1"
            onClick={() => {
              setEditing(null);
              setFormOpen(true);
            }}
          >
            <Plus className="h-4 w-4" /> {t("inventory.add")}
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-on-surface-variant" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("inventory.searchPlaceholder")}
            className="pl-9"
          />
        </div>
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="h-11 w-full rounded-xl border border-glass-border bg-glass-surface px-3 text-base text-on-surface shadow-sm outline-none backdrop-blur-md focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 sm:w-56 md:text-sm"
        >
          <option value="">{t("contacts.types.all")}</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>

      {isError ? (
        <p className="glass-panel clip-rounded-lg rounded-lg p-6 text-center text-sm text-on-surface-variant">
          {t("errors.generic")}
        </p>
      ) : isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : products.length === 0 ? (
        <p className="glass-panel clip-rounded-lg rounded-lg p-8 text-center text-sm text-on-surface-variant">
          {t("inventory.empty")}
        </p>
      ) : (
        <div className="space-y-2">
          {products.map((p) => {
            const categoryName = categories.find((c) => c.id === p.category)?.name;
            return (
              <ProductCard
                key={p.id}
                product={p}
                categoryName={categoryName}
                onEdit={() => {
                  setEditing(p);
                  setFormOpen(true);
                }}
                onAdjust={() => setAdjusting(p)}
                onDelete={() => setDeleting(p)}
              />
            );
          })}
        </div>
      )}

      <ProductFormDialog
        product={editing}
        open={formOpen}
        onOpenChange={setFormOpen}
      />
      <CategoryManagerDialog open={categoriesOpen} onOpenChange={setCategoriesOpen} />
      <StockAdjustDialog product={adjusting} open={Boolean(adjusting)} onOpenChange={(o) => { if (!o) setAdjusting(null); }} />
      <ConfirmDeleteDialog
        open={Boolean(deleting)}
        onOpenChange={(o) => { if (!o) setDeleting(null); }}
        itemName={t("inventory.product")}
        itemLabel={deleting?.name}
        pending={remove.isPending}
        onConfirm={() => {
          if (deleting) remove.mutate(deleting.id);
        }}
      />
    </div>
  );
}