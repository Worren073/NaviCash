import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { Briefcase, GraduationCap } from "lucide-react";
import { HomeIcon } from "@/components/icons";

import { GlassPopover } from "@/components/ui/glass-popover";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { queryKeys } from "@/hooks/use-queries";
import { resetNaviTour } from "@/features/assistant/navi-tour-content";
import { useNavView } from "@/features/navigation/nav-view";
import { BOTTOM_NAV, PRIMARY_NAV, SECONDARY_NAV } from "@/features/navigation/nav-config";

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

export function useReplayTour() {
  const queryClient = useQueryClient();

  return () => {
    // Limpia el "visto" por ruta y vuelve a marcar el tour como pendiente para
    // que Navi lo muestre de nuevo al navegar.
    resetNaviTour();
    void api
      .patch("/auth/me", { is_onboarded: false })
      .then(() => queryClient.invalidateQueries({ queryKey: queryKeys.me }))
      .catch(() => {
        // El localStorage ya se limpió; el PATCH falla no bloquea el reinicio.
      });
  };
}

export function AppMenu({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const replayTour = useReplayTour();
  const { view, changeView } = useNavView();

  // Enlaces de la vista activa que ya viven en la bottom-nav no se repiten
  // aquí: el menú lista solo los que faltan (personales: Mensualidades/Compras;
  // negocio: Chats/Pedidos/Inventario/Cobranza).
  const inBottomNav = new Set(BOTTOM_NAV[view].map((item) => item.to));
  const menuItems = [...PRIMARY_NAV[view], ...SECONDARY_NAV[view]].filter(
    (item) => !inBottomNav.has(item.to)
  );

  return (
    <GlassPopover open={open} onClose={onClose} className="w-60 bg-white/90 backdrop-blur-[60px]">
      <div className="p-2">
        {/* Conmutador de vista (móvil y tablet compacta: el menú se abre < lg,
            y en md+ la TopBar ya muestra el segmented, por eso se oculta aquí). */}
        <div className="md:hidden">
          <p className="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-on-surface-variant">
            {t("menu.view")}
          </p>
          <button
            type="button"
            onClick={() => {
              changeView("personal");
              onClose();
            }}
            className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors hover:bg-surface-container-high ${
              view === "personal" ? "bg-surface-container-high text-primary" : "text-on-surface"
            }`}
            role="menuitem"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-surface-container-high">
              <HomeIcon className="h-5 w-5" />
            </span>
            {t("nav.personal")}
          </button>
          <button
            type="button"
            onClick={() => {
              changeView("business");
              onClose();
            }}
            className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors hover:bg-surface-container-high ${
              view === "business" ? "bg-surface-container-high text-primary" : "text-on-surface"
            }`}
            role="menuitem"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-surface-container-high">
              <Briefcase className="h-5 w-5 text-primary" />
            </span>
            {t("nav.business")}
          </button>
        </div>
        <p className="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-on-surface-variant">
          {t("menu.title")}
        </p>
        {menuItems.map((item) => {
          const Icon = item.icon;
          return (
            <MenuLink
              key={item.to}
              to={item.to}
              onNavigate={onClose}
              label={t(item.label)}
              icon={
                <Icon
                  className={cn("h-5 w-5", item.iconClassName ?? "text-on-surface-variant")}
                />
              }
            />
          );
        })}
        <button
          type="button"
          onClick={() => {
            replayTour();
            onClose();
          }}
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
