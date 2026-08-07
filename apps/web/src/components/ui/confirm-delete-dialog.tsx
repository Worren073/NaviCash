import { useTranslation } from "react-i18next";
import { TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface ConfirmDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Sustantivo del elemento a eliminar (ej. "billetera", "meta", "mensualidad"). */
  itemName: string;
  /** Nombre concreto del elemento (ej. "Ahorro vacaciones"). */
  itemLabel?: string;
  onConfirm: () => void;
  /** true si la petición de borrado está en curso. */
  pending?: boolean;
}

/**
 * Diálogo glass de confirmación de borrado: "¿Eliminar este {itemName}?"
 * Reutilizado por billeteras, cuentas de ahorro, metas y mensualidades.
 */
export function ConfirmDeleteDialog({
  open,
  onOpenChange,
  itemName,
  itemLabel,
  onConfirm,
  pending = false,
}: ConfirmDeleteDialogProps) {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-status-delayed/15">
              <TriangleAlert className="h-5 w-5 text-status-delayed" />
            </span>
            {t("common.deleteConfirmTitle")}
          </DialogTitle>
          <DialogDescription>
            {t("common.deleteConfirmMessage", {
              item: itemLabel ? `${itemName} «${itemLabel}»` : itemName,
            })}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={pending}>
            {t("common.cancel")}
          </Button>
          <Button variant="destructive" onClick={onConfirm} disabled={pending}>
            {pending ? t("common.loading") : t("common.delete")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
