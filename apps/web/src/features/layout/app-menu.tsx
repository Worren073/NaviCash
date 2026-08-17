import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { CalendarRange, GraduationCap, PiggyBank } from "lucide-react";

import { GlassPopover } from "@/components/ui/glass-popover";
import { api } from "@/lib/api";
import { queryKeys } from "@/hooks/use-queries";
import { resetNaviTour } from "@/features/assistant/navi-tour-content";

function MenuLink({
  to,
  label,
  icon,
  onNavigate,
}: {
  to: string;
  label: string;
  icon: React.ReactNode;
  onNavigate: () => void;
}) {
  return (
    <Link
      to={to}
      onClick={onNavigate}
      className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
      role="menuitem"
    >
      <span className="flex h-9 w-9 items-center justify-center rounded-full bg-surface-container-high">
        {icon}
      </span>
      {label}
    </Link>
  );
}

export function AppMenu({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  function replayTour() {
    // Limpia el "visto" por ruta y vuelve a marcar el tour como pendiente para
    // que Navi lo muestre de nuevo al navegar.
    resetNaviTour();
    void api
      .patch("/auth/me", { is_onboarded: false })
      .then(() => queryClient.invalidateQueries({ queryKey: queryKeys.me }))
      .catch(() => {
        // El localStorage ya se limpió; el PATCH falla no bloquea el reinicio.
      });
    onClose();
  }

  return (
    <GlassPopover open={open} onClose={onClose} className="w-60 bg-white/90 backdrop-blur-[60px]">
      <div className="p-2">
        <p className="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-on-surface-variant">
          {t("menu.title")}
        </p>
        <MenuLink to="/savings" onNavigate={onClose} label={t("menu.savings")} icon={<PiggyBank className="h-5 w-5 text-emerald-500" />} />
        <MenuLink to="/subscriptions" onNavigate={onClose} label={t("menu.subscriptions")} icon={<CalendarRange className="h-5 w-5 text-primary" />} />
        <button
          type="button"
          onClick={replayTour}
          className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
          role="menuitem"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-surface-container-high">
            <GraduationCap className="h-5 w-5 text-on-surface-variant" />
          </span>
          {t("menu.replayTour")}
        </button>
      </div>
    </GlassPopover>
  );
}
