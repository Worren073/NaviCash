import type { ComponentType } from "react";
import { Briefcase, CalendarRange, FileText, ListChecks, PiggyBank, Users } from "lucide-react";

import {
  HomeIcon,
  SendHorizontalIcon,
  UserIcon,
  WalletIcon,
} from "@/components/icons";
import type { NavView } from "@/features/navigation/nav-view";

export type NavItem = {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string; size?: number }>;
  matchEnd?: boolean;
};

/** Módulos principales de la sidebar según la vista activa.
 *  El perfil se mueve al TopBar en desktop/tablet, pero se mantiene en bottom-nav móvil.
 */
export const PRIMARY_NAV: Record<NavView, readonly NavItem[]> = {
  personal: [
    { to: "/", label: "nav.dashboard", icon: HomeIcon, matchEnd: true },
    { to: "/wallets", label: "nav.wallets", icon: WalletIcon },
    { to: "/transactions", label: "nav.transactions", icon: SendHorizontalIcon },
  ],
  business: [
    { to: "/business", label: "nav.business", icon: Briefcase, matchEnd: true },
    { to: "/transactions", label: "nav.transactions", icon: SendHorizontalIcon },
    { to: "/business/contacts", label: "nav.contacts", icon: Users },
    { to: "/business/invoices", label: "nav.invoices", icon: FileText },
  ],
};

/** Sección secundaria ("Más/Menú") de la sidebar: el negocio no la tiene. */
export const SECONDARY_NAV: Record<NavView, readonly NavItem[]> = {
  personal: [
    { to: "/savings", label: "menu.savings", icon: PiggyBank },
    { to: "/subscriptions", label: "menu.subscriptions", icon: CalendarRange },
    { to: "/checklists", label: "menu.checklists", icon: ListChecks },
  ],
  business: [],
};

// La bottom-nav intercala el botón "+" tras el segundo elemento.
// El perfil se mantiene aquí para móvil, aunque en desktop/tablet vive en el TopBar.
export const BOTTOM_NAV: Record<NavView, readonly NavItem[]> = {
  personal: [
    ...PRIMARY_NAV.personal,
    { to: "/profile", label: "nav.profile", icon: UserIcon },
  ],
  business: [
    ...PRIMARY_NAV.business,
    { to: "/profile", label: "nav.profile", icon: UserIcon },
  ],
};