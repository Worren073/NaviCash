import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import type { ComponentType } from "react";
import { GraduationCap } from "lucide-react";

import {
  LogoutIcon,
} from "@/components/icons";
import { AddButton } from "@/features/layout/add-button";
import { useReplayTour } from "@/features/layout/app-menu";
import { useNavView } from "@/features/navigation/nav-view";
import { PRIMARY_NAV, SECONDARY_NAV } from "@/features/navigation/nav-config";
import { api, setAccessToken } from "@/lib/api";
import { cn } from "@/lib/utils";

const EASE: [number, number, number, number] = [0.4, 0, 0.2, 1];
const CLOSE_DELAY_MS = 400;
const ANIM_CLS = "transition-all duration-[450ms] ease-[cubic-bezier(0.4,0,0.2,1)]";
// Píldora activa sin dimensiones relativas al contenedor en plena transición:
// el ancho expandido del rail (lg:w-64 = 256px menos px-3×2 del aside) y el alto
// del link (h-10) son constantes, por lo que la animación es simétrica y limpia.
const PILL_EXPANDED = { left: 0, top: 0, width: 232, height: 40 } as const;
const PILL_RADIUS = 20; // alto h-10 (40px) / 2 → extremos totalmente redondeados (cápsula)
const PILL_COLLAPSED = { left: 4, top: 2, width: 36, height: 36 } as const;

function SidebarLink({
  to,
  label,
  icon: Icon,
  matchEnd,
  expanded,
}: {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string; size?: number }>;
  matchEnd?: boolean;
  expanded: boolean;
}) {
  const { t } = useTranslation();
  const location = useLocation();
  const active = matchEnd ? location.pathname === to : location.pathname.startsWith(to);
  return (
    <Link
      to={to}
      aria-label={t(label)}
      title={t(label)}
      aria-current={active ? "page" : undefined}
      className={cn(
        "relative flex h-10 items-center gap-3 rounded-xl px-3 text-sm font-medium transition-colors",
        active ? "text-on-primary" : "text-on-surface hover:bg-surface-container-high"
      )}
    >
      {active && (
        <motion.span
          layoutId="nav-active-rail"
          className="absolute z-0 bg-primary"
          initial={false}
          animate={
            expanded
              ? { ...PILL_EXPANDED, borderRadius: PILL_RADIUS }
              : { ...PILL_COLLAPSED, borderRadius: 9999 }
          }
          transition={{ duration: 0.45, ease: EASE }}
        />
      )}
      <Icon size={20} className="relative z-10 shrink-0" />
      <span
        className={cn(
          "relative z-10 inline-block overflow-hidden whitespace-nowrap",
          ANIM_CLS,
          expanded ? "translate-x-0 opacity-100" : "-translate-x-3 opacity-0"
        )}
      >
        {t(label)}
      </span>
    </Link>
  );
}

function ReplayTourButton({ expanded }: { expanded: boolean }) {
  const { t } = useTranslation();
  const replayTour = useReplayTour();
  return (
    <button
      type="button"
      onClick={replayTour}
      className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
    >
      <GraduationCap size={20} className="shrink-0 text-on-surface-variant" />
      <span
        className={cn(
          "inline-block overflow-hidden whitespace-nowrap",
          ANIM_CLS,
          expanded ? "translate-x-0 opacity-100" : "-translate-x-3 opacity-0"
        )}
      >
        {t("menu.replayTour")}
      </span>
    </button>
  );
}

function LogoutButton({ expanded }: { expanded: boolean }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const logout = useMutation({
    mutationFn: () => api.post<{ detail: string }>("/auth/logout"),
    onSuccess: () => {
      setAccessToken(null);
      queryClient.clear();
      navigate("/login");
    },
  });

  return (
    <button
      type="button"
      onClick={() => logout.mutate()}
      disabled={logout.isPending}
      aria-label={t("auth.logout")}
      title={t("auth.logout")}
      className="flex h-10 w-full items-center gap-3 rounded-xl px-3 text-sm font-medium text-error transition-colors hover:bg-error-container/40 disabled:opacity-60"
    >
      <LogoutIcon size={20} className="shrink-0" />
      <span
        className={cn(
          "inline-block overflow-hidden whitespace-nowrap",
          ANIM_CLS,
          expanded ? "translate-x-0 opacity-100" : "-translate-x-3 opacity-0"
        )}
      >
        {logout.isPending ? t("common.loading") : t("auth.logout")}
      </span>
    </button>
  );
}

export function Sidebar({ onVoiceOpen }: { onVoiceOpen: () => void }) {
  const { t } = useTranslation();
  const { view } = useNavView();
  const [expanded, setExpanded] = useState(false);
  const closeTimer = useRef<number | null>(null);

  function clearClose() {
    if (closeTimer.current !== null) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  }

  function handleEnter() {
    clearClose();
    setExpanded(true);
  }

  function handleLeave() {
    clearClose();
    closeTimer.current = window.setTimeout(() => {
      closeTimer.current = null;
      setExpanded(false);
    }, CLOSE_DELAY_MS);
  }

  useEffect(
    () => () => {
      if (closeTimer.current !== null) {
        window.clearTimeout(closeTimer.current);
      }
    },
    []
  );

  return (
    <aside
      aria-label="Navegación principal"
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
      onFocus={handleEnter}
      onBlur={handleLeave}
      className={cn(
        "fixed-glass hidden lg:fixed lg:left-4 lg:top-[calc(env(safe-area-inset-top)+4.5rem)] lg:bottom-[calc(env(safe-area-inset-bottom)+1rem)] lg:z-[60] lg:flex lg:flex-col lg:gap-1 lg:overflow-hidden lg:rounded-3xl lg:border lg:border-glass-border lg:bg-glass-surface/80 lg:px-3 lg:py-4 lg:shadow-[0_8px_32px_rgba(15,23,42,0.25)] lg:backdrop-blur-2xl lg:transition-[width] lg:duration-[450ms] lg:ease-[cubic-bezier(0.4,0,0.2,1)]",
        expanded ? "lg:w-64" : "lg:w-[4.75rem]"
      )}
    >
      <nav className="flex flex-col gap-1">
        {PRIMARY_NAV[view].map((item) => (
          <SidebarLink key={item.to} {...item} expanded={expanded} />
        ))}
        <div
          className={cn(
            "flex items-center gap-3 py-1.5",
            ANIM_CLS,
            expanded ? "px-3" : "px-1"
          )}
        >
          <AddButton
            onVoiceOpen={onVoiceOpen}
            className="h-9 w-9 shrink-0 translate-y-0 shadow-md shadow-primary/20"
            iconClassName="h-5 w-5"
          />
          <span
            className={cn(
              "inline-block overflow-hidden whitespace-nowrap text-sm font-medium text-on-surface",
              ANIM_CLS,
              expanded ? "translate-x-0 opacity-100" : "-translate-x-3 opacity-0"
            )}
          >
            {t("nav.add")}
          </span>
        </div>
      </nav>
      {SECONDARY_NAV[view].length > 0 && (
        <div className="mt-4 border-t border-glass-border pt-3">
          <p
            className={cn(
              "overflow-hidden whitespace-nowrap px-3 pb-1 pt-1 text-[11px] font-semibold uppercase tracking-wider text-on-surface-variant",
              ANIM_CLS,
              expanded ? "translate-x-0 opacity-100" : "-translate-x-3 opacity-0"
            )}
          >
            {t("menu.title")}
          </p>
          <nav className="flex flex-col gap-1">
            {SECONDARY_NAV[view].map((item) => (
              <SidebarLink key={item.to} {...item} expanded={expanded} />
            ))}
          </nav>
        </div>
      )}
      <div className="mt-auto border-t border-glass-border pt-2">
        <ReplayTourButton expanded={expanded} />
      </div>
      <div className="border-t border-glass-border pt-2">
        <LogoutButton expanded={expanded} />
      </div>
    </aside>
  );
}