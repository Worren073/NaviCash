import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { FileText, ShieldCheck, X, AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { TERMS_CONTENT, PRIVACY_CONTENT } from "@/features/legal/legal-content";
import { renderLegalMarkdown } from "@/features/legal/render-legal";

interface LegalAcceptanceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAccept: () => void;
  /** Si se pasa, se muestra un botón secundario de rechazo (p. ej. en login). */
  onDecline?: () => void;
  /** Muestra la etiqueta de "Actualización requerida" en el encabezado. */
  needsReacceptance?: boolean;
  /** Versión vigente de los términos que se muestran. */
  version?: string;
}

interface LegalDocumentDto {
  doc_type: "terms" | "privacy";
  title: string;
  content: string;
}

export default function LegalAcceptanceDialog({
  open,
  onOpenChange,
  onAccept,
  onDecline,
  needsReacceptance = false,
  version = "v1-2026-08",
}: LegalAcceptanceDialogProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<"terms" | "privacy">("terms");
  const [termsScrolled, setTermsScrolled] = useState(false);
  const [docs, setDocs] = useState<Record<string, LegalDocumentDto>>({});

  useEffect(() => {
    if (open) {
      setActiveTab("terms");
      setTermsScrolled(false);
      let cancelled = false;
      api
        .get<LegalDocumentDto[]>("/legal")
        .then((list) => {
          if (cancelled) return;
          const byType: Record<string, LegalDocumentDto> = {};
          for (const doc of list) byType[doc.doc_type] = doc;
          setDocs(byType);
        })
        .catch(() => {
          /* Usamos el contenido estático como respaldo si falla la carga. */
        });
      return () => {
        cancelled = true;
      };
    }
  }, [open]);

  const content =
    activeTab === "terms"
      ? docs.terms?.content ?? TERMS_CONTENT.body
      : docs.privacy?.content ?? PRIVACY_CONTENT.body;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-2">
            <span>{t("auth.termsModalTitle")}</span>
            {needsReacceptance && (
              <span className="flex items-center gap-1 rounded-full bg-yellow-100 px-3 py-0.5 text-xs font-medium text-black dark:bg-yellow-200">
                <AlertTriangle className="h-3.5 w-3.5" />
                {t("profile.legalUpdateRequired")}
              </span>
            )}
          </DialogTitle>
          <DialogDescription>{t("auth.termsModalHint")}</DialogDescription>
        </DialogHeader>

        <div className="border-b border-glass-border">
          <nav className="flex gap-1 pb-1" role="tablist">
            <button
              role="tab"
              aria-selected={activeTab === "terms"}
              aria-controls="terms-panel"
              id="terms-tab"
              onClick={() => setActiveTab("terms")}
              className={`flex-1 rounded-t-lg px-3 py-2 text-sm font-medium transition-colors ${
                activeTab === "terms"
                  ? "bg-primary text-on-primary"
                  : "text-on-surface-variant hover:bg-surface-container-high"
              }`}
            >
              <FileText className="mr-1 inline h-4 w-4" /> {t("auth.termsTab")}
            </button>
            <button
              role="tab"
              aria-selected={activeTab === "privacy"}
              aria-controls="privacy-panel"
              id="privacy-tab"
              onClick={() => setActiveTab("privacy")}
              className={`flex-1 rounded-t-lg px-3 py-2 text-sm font-medium transition-colors ${
                activeTab === "privacy"
                  ? "bg-primary text-on-primary"
                  : "text-on-surface-variant hover:bg-surface-container-high"
              }`}
            >
              <ShieldCheck className="mr-1 inline h-4 w-4" /> {t("auth.privacyTab")}
            </button>
          </nav>
        </div>

        <div
          className="max-h-[55dvh] space-y-4 overflow-y-auto pr-1 pt-4"
          onScroll={(e) => {
            const el = e.currentTarget;
            if (el.scrollTop + el.clientHeight >= el.scrollHeight - 8) {
              setTermsScrolled(true);
            }
          }}
          role="tabpanel"
          id={`${activeTab}-panel`}
          aria-labelledby={`${activeTab}-tab`}
        >
          <div className="mb-4 rounded-lg border border-primary/20 bg-primary/10 p-3">
            <p className="text-sm text-on-surface-variant">
              <strong>{t("auth.termsVersion")}:</strong> {version}
            </p>
          </div>
          <div className="prose prose-sm max-w-none text-on-surface-variant">
            {renderLegalMarkdown(content)}
          </div>
        </div>

        <DialogFooter className="flex flex-col gap-2">
          <Button className="w-full" disabled={!termsScrolled} onClick={onAccept}>
            {t("auth.termsAccept")}
          </Button>
          {onDecline && (
            <Button
              variant="outline"
              className="w-full border-red-200 text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/20"
              onClick={onDecline}
            >
              <X className="mr-1 h-4 w-4" />
              {t("auth.termsDeclinedLogout")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}