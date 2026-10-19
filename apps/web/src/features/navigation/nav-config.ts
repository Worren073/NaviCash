import type { ComponentType } from "react";
import { BarChart3, Briefcase, CalendarRange, FileText, HandCoins, ListChecks, MessageCircle, Package, PiggyBank, ShoppingCart, Users } from "lucide-react";

import {
  HomeIcon,
  SendHorizontalIcon,
  WalletIcon,
} from "@/components/icons";
import type { NavView } from "@/features/navigation/nav-view";

export type NavItem = {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string; size?: number }>;
  matchEnd?: boolean;
  /** Clases Tailwind de color para el ícono (usado por el menú móvil). */
  iconClassName?: string;
};

/** Módulos principales de la sidebar según la vista activa.
 *  El perfil vive solo en el TopBar (también en móvil), nunca en bottom-nav.
 */
export const PRIMARY_NAV: Record<NavView, readonly NavItem[]> = {
  personal: [
    { to: "/", label: "nav.dashboard", icon: HomeIcon, matchEnd: true },
    { to: "/wallets", label: "nav.wallets", icon: WalletIcon },
    { to: "/transactions", label: "nav.transactions", icon: SendHorizontalIcon },
  ],
  business: [
    { to: "/business", label: "nav.business", icon: Briefcase, matchEnd: true },
    { to: "/business/analytics", label: "nav.analytics", icon: BarChart3 },
    { to: "/transactions", label: "nav.transactions", icon: SendHorizontalIcon },
    { to: "/business/contacts", label: "nav.contacts", icon: Users },
    { to: "/business/chats", label: "nav.chats", icon: MessageCircle, iconClassName: "text-emerald-500" },
    { to: "/business/invoices", label: "nav.invoices", icon: FileText },
    { to: "/business/orders", label: "nav.orders", icon: ShoppingCart, iconClassName: "text-primary" },
    { to: "/business/inventory", label: "nav.inventory", icon: Package, iconClassName: "text-sky-500" },
    { to: "/business/collection", label: "nav.collection", icon: HandCoins, iconClassName: "text-amber-500" },
  ],
};

/** Sección secundaria ("Más/Menú") de la sidebar: el negocio no la tiene. */
export const SECONDARY_NAV: Record<NavView, readonly NavItem[]> = {
  personal: [
    { to: "/savings", label: "menu.savings", icon: PiggyBank, iconClassName: "text-emerald-500" },
    { to: "/subscriptions", label: "menu.subscriptions", icon: CalendarRange, iconClassName: "text-primary" },
    { to: "/checklists", label: "menu.checklists", icon: ListChecks, iconClassName: "text-sky-500" },
  ],
  business: [],
};

// La bottom-nav móvil muestra exactamente 5 elementos por vista: 4 enlaces +
// el botón "+" en personal, y 5 enlaces sin "+" en negocio (el "+" vive solo en
// la vista personal). El perfil no aparece aquí: ya está en el TopBar. Cobranza,
// Inventario, Chats, Pedidos (negocio) y Mensualidades/Compras (personal) viven
// en el menú móvil y en la sidebar de escritorio.
export const BOTTOM_NAV: Record<NavView, readonly NavItem[]> = {
  personal: [
    ...PRIMARY_NAV.personal,
    { to: "/savings", label: "menu.savings", icon: PiggyBank },
  ],
  business: [
    { to: "/business", label: "nav.business", icon: Briefcase, matchEnd: true },
    { to: "/transactions", label: "nav.transactions", icon: SendHorizontalIcon },
    { to: "/business/contacts", label: "nav.contacts", icon: Users },
    { to: "/business/invoices", label: "nav.invoices", icon: FileText },
    { to: "/business/analytics", label: "nav.analytics", icon: BarChart3 },
  ],
};