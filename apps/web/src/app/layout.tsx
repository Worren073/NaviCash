import { Link, Outlet, useLocation } from "react-router-dom";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "motion/react";
import { Plus } from "lucide-react";
import {
  FilledBellIcon,
  HomeIcon,
  ListIcon,
  SendHorizontalIcon,
  UserIcon,
  WalletIcon,
} from "@/components/icons";
import type { AnimatedIconHandle } from "@/components/icons";
import { AnimatedIconButton } from "@/components/ui/animated-icon-button";
import { NotificationsPopover } from "@/features/notifications/notifications-popover";
import { AppMenu } from "@/features/layout/app-menu";
import { useNotifications } from "@/hooks/use-queries";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/", label: "nav.dashboard", icon: HomeIcon },
  { to: "/wallets", label: "nav.wallets", icon: WalletIcon },
] as const;

function NotificationBadge() {
  const { data } = useNotifications();
  const unread = data?.unread_count ?? 0;
  if (unread === 0) return null;
  return (
    <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-status-delayed px-1 text-[10px] font-bold text-white">
      {unread > 9 ? "9+" : unread}
    </span>
  );
}

function TopBar() {
  const { t } = useTranslation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);

  return (
    <header className="fixed inset-x-0 top-0 z-50 flex w-full items-center justify-between border-b border-glass-border bg-glass-surface px-5 py-4 shadow-sm backdrop-blur-xl">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-sm font-bold text-on-primary shadow-sm">
          N
        </div>
        <h1 className="text-xl font-bold tracking-tight text-primary">{t("app.name")}</h1>
      </div>
      <div className="flex items-center gap-1">
        <div className="relative z-50">
          <AnimatedIconButton
            icon={ListIcon}
            label={t("menu.title")}
            onClick={() => setMenuOpen((v) => {
              setNotifOpen(false);
              return !v;
            })}
          />
          <AppMenu open={menuOpen} onClose={() => setMenuOpen(false)} />
        </div>
        <div className="relative z-50">
          <AnimatedIconButton
            icon={FilledBellIcon}
            label={t("common.notifications")}
            onClick={() => setNotifOpen((v) => {
              setMenuOpen(false);
              return !v;
            })}
          >
            <NotificationBadge />
          </AnimatedIconButton>
          <NotificationsPopover open={notifOpen} onClose={() => setNotifOpen(false)} />
        </div>
      </div>
    </header>
  );
}

function BottomNav() {
  const { t } = useTranslation();
  return (
    <nav
      aria-label="Navegación principal"
      className="fixed bottom-4 left-1/2 z-50 flex w-[calc(100%-2.5rem)] max-w-md -translate-x-1/2 items-center justify-around rounded-full border border-glass-border bg-glass-surface p-2 shadow-[0_8px_32px_0_rgba(0,0,0,0.1)] backdrop-blur-2xl"
    >
      {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
        <NavLink key={to} to={to} label={label} icon={Icon} matchEnd={to === "/"} />
      ))}
      <Link
        to="/operations/new"
        aria-label={t("nav.add")}
        className="flex h-14 w-14 -translate-y-1.5 items-center justify-center rounded-full border-2 border-surface bg-primary text-white shadow-lg shadow-primary/30 transition-all hover:opacity-90 active:scale-90"
      >
        <Plus className="h-7 w-7" style={{ strokeWidth: 2.5 }} />
      </Link>
      <NavLink to="/transactions" label="nav.transactions" icon={SendHorizontalIcon} />
      <NavLink to="/profile" label="nav.profile" icon={UserIcon} />
    </nav>
  );
}

function NavLink({
  to,
  label,
  icon: Icon,
  matchEnd,
}: {
  to: string;
  label: string;
  icon: typeof HomeIcon;
  matchEnd?: boolean;
}) {
  const { t } = useTranslation();
  const location = useLocation();
  const ref = useRef<AnimatedIconHandle>(null);
  const active = matchEnd ? location.pathname === to : location.pathname.startsWith(to);
  return (
    <Link
      to={to}
      aria-label={t(label)}
      title={t(label)}
      onClick={() => ref.current?.startAnimation()}
      className={cn(
        "relative flex h-12 w-12 items-center justify-center rounded-full",
        active ? "text-on-primary" : "text-on-surface-variant"
      )}
    >
      {active && (
        <motion.div
          layoutId="nav-active-pill"
          className="absolute inset-0 rounded-full bg-primary"
          transition={{ type: "spring", stiffness: 500, damping: 40 }}
        />
      )}
      <Icon ref={ref} size={24} className="relative z-10" />
    </Link>
  );
}

export default function AppLayout() {
  const location = useLocation();
  return (
    <div className="min-h-dvh pb-28">
      <TopBar />
      <main className="mx-auto w-full max-w-lg px-5 pb-8 pt-20">
        <div key={location.pathname} className="view-enter">
          <Outlet />
        </div>
      </main>
      <BottomNav />
    </div>
  );
}