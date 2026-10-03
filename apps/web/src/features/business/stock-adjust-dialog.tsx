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
import { api, ApiErrorClass } from "@/lib/api";
import { queryKeys } from "@/hooks/use-queries";
import type { Product } from "@/lib/types";

export function StockAdjustDialog({
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
  const [delta, setDelta] = useState("");
  const [reason, setReason] = useState("");

  useEffect(() => {
    if (open) {
      setDelta("");
      setReason("");
    }
  }, [open]);

  const deltaNum = Number(delta) || 0;
  const wouldBeNegative = (Number(product?.stock_quantity ?? 0) + deltaNum) < 0;
  // Con la unidad «Unidad» las existencias se manejan en enteros.
  const needsInteger = product?.unit === "unidad";
  const validationError = useMemo(() => {
    if (!delta || !Number.isFinite(deltaNum) || deltaNum === 0)
      return t("inventory.adjustDeltaError");
    if (needsInteger && !Number.isInteger(deltaNum))
      return t("inventory.integerRequired");
    if (wouldBeNegative) return t("inventory.adjustErrorNegative");
    if (!reason.trim()) return t("inventory.adjustReasonError");
    return null;
  }, [delta, deltaNum, needsInteger, wouldBeNegative, reason, t]);

  const adjust = useMutation({
    mutationFn: () =>
      api.post(`/business/products/${product!.id}/adjust/`, {
        delta,
        reason: reason.trim(),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.products });
      onOpenChange(false);
      sileo.success({ title: t("inventory.adjusted") });
    },
    onError: (err) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("inventory.adjustError");
      sileo.error({ title: msg });
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{t("inventory.adjustTitle")}</DialogTitle>
          <DialogDescription>
            {product
              ? `${product.name} · ${t("inventory.stock")}: ${product.stock_quantity}`
              : ""}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-on-surface">
              {t("inventory.adjustDelta")}
            </span>
            <Input
              type="number"
              inputMode={needsInteger ? "numeric" : "decimal"}
              value={delta}
              onChange={(e) => setDelta(e.target.value)}
              placeholder="+5"
            />
            <span className="mt-1 block text-xs text-on-surface-variant">
              {t("inventory.adjustDeltaHint")}
            </span>
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-on-surface">
              {t("inventory.adjustReason")}
            </span>
            <Input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={t("inventory.adjustReasonPlaceholder")}
            />
          </label>
          {validationError && <p className="text-sm text-destructive">{validationError}</p>}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={adjust.isPending}>
            {t("common.cancel")}
          </Button>
          <Button
            variant="glow"
            onClick={() => adjust.mutate()}
            disabled={Boolean(validationError) || adjust.isPending}
          >
            {adjust.isPending ? t("common.loading") : t("inventory.adjust")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}