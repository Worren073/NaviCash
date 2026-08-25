import { useState } from "react";
import { useTranslation } from "react-i18next";
import { BrainCircuit, BookOpen, Ban } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

type NaviLearningMode = "full" | "manual" | "none";

interface NaviLearningConsentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (mode: NaviLearningMode) => void;
}

const MODE_OPTIONS: Array<{
  mode: NaviLearningMode;
  icon: typeof BrainCircuit;
  titleKey: string;
  descKey: string;
  color: string;
  activeColor: string;
}> = [
  {
    mode: "full",
    icon: BrainCircuit,
    titleKey: "profile.naviConsentFull",
    descKey: "profile.naviConsentFullDesc",
    color: "border-glass-border bg-glass-surface",
    activeColor: "border-primary bg-primary/10 ring-2 ring-primary/30",
  },
  {
    mode: "manual",
    icon: BookOpen,
    titleKey: "profile.naviConsentManual",
    descKey: "profile.naviConsentManualDesc",
    color: "border-glass-border bg-glass-surface",
    activeColor: "border-secondary bg-secondary/10 ring-2 ring-secondary/30",
  },
  {
    mode: "none",
    icon: Ban,
    titleKey: "profile.naviConsentNone",
    descKey: "profile.naviConsentNoneDesc",
    color: "border-glass-border bg-glass-surface",
    activeColor: "border-on-surface-variant bg-surface-container/60 ring-2 ring-on-surface-variant/30",
  },
];

export function NaviLearningConsentDialog({
  open,
  onOpenChange,
  onConfirm,
}: NaviLearningConsentDialogProps) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<NaviLearningMode>("full");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <BrainCircuit className="h-5 w-5 text-primary" />
            {t("profile.naviConsentTitle")}
          </DialogTitle>
          <DialogDescription className="space-y-2 pt-2">
            <p>{t("profile.naviConsentDesc1")}</p>
            <p className="font-medium text-on-surface">
              {t("profile.naviConsentDesc2")}
            </p>
            <p>{t("profile.naviConsentDesc3")}</p>
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2 py-2">
          {MODE_OPTIONS.map((opt) => {
            const Icon = opt.icon;
            const isActive = selected === opt.mode;
            return (
              <button
                key={opt.mode}
                type="button"
                onClick={() => setSelected(opt.mode)}
                className={cn(
                  "flex w-full items-start gap-3 rounded-xl border p-3 text-left transition-all",
                  isActive ? opt.activeColor : opt.color,
                )}
              >
                <Icon
                  className={cn(
                    "mt-0.5 h-5 w-5 shrink-0",
                    isActive ? "text-primary" : "text-on-surface-variant",
                  )}
                />
                <div className="min-w-0">
                  <p
                    className={cn(
                      "text-sm font-medium",
                      isActive ? "text-on-surface" : "text-on-surface",
                    )}
                  >
                    {t(opt.titleKey)}
                  </p>
                  <p className="mt-0.5 text-xs text-on-surface-variant">
                    {t(opt.descKey)}
                  </p>
                </div>
              </button>
            );
          })}
        </div>

        <DialogFooter>
          <Button
            onClick={() => onConfirm(selected)}
            className="w-full"
          >
            {t("profile.naviConsentConfirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
