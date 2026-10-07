import type { ComponentType } from "react";
import { Briefcase, CalendarRange, FileText, HandCoins, ListChecks, Package, PiggyBank, ShoppingCart, Users } from "lucide-react";

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
    { to: "/business/orders", label: "nav.orders", icon: ShoppingCart },
    { to: "/business/inventory", label: "nav.inventory", icon: Package },
    { to: "/business/collection", label: "nav.collection", icon: HandCoins },
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

// La bottom-nav móvil muestra exactamente 5 iconos por vista: 4 enlaces + el
// botón "+" en personal, y 5 enlaces sin "+" en negocio (el "+" vive solo en
// la vista personal). El perfil se mantiene aquí para móvil, aunque en
// desktop/tablet vive en el TopBar. Cobranza e Inventario quedan fuera del
// bottom-nav de negocio: siguen en la sidebar de escritorio y en los accesos
// rápidos del dashboard de negocio.
export const BOTTOM_NAV: Record<NavView, readonly NavItem[]> = {
  personal: [
    ...PRIMARY_NAV.personal,
    { to: "/profile", label: "nav.profile", icon: UserIcon },
  ],
  business: [
    { to: "/business", label: "nav.business", icon: Briefcase, matchEnd: true },
    { to: "/transactions", label: "nav.transactions", icon: SendHorizontalIcon },
    { to: "/business/contacts", label: "nav.contacts", icon: Users },
    { to: "/business/invoices", label: "nav.invoices", icon: FileText },
    { to: "/profile", label: "nav.profile", icon: UserIcon },
  ],
};