import { Link, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";
import {
  FilledBellIcon,
  HomeIcon,
  SendHorizontalIcon,
  UserIcon,
  WalletIcon,
} from "@/components/icons";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/", label: "nav.dashboard", icon: HomeIcon },
  { to: "/wallets", label: "nav.wallets", icon: WalletIcon },
] as const;

function TopBar() {
  const { t } = useTranslation();
  return (
    <header className="fixed inset-x-0 top-0 z-50 flex w-full items-center justify-between border-b border-glass-border bg-glass-surface px-5 py-4 shadow-sm backdrop-blur-xl">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-sm font-bold text-on-primary shadow-sm">
          N
        </div>
        <h1 className="text-xl font-bold tracking-tight text-primary">{t("app.name")}</h1>
      </div>
      <button
        type="button"
        aria-label={t("common.notifications") ?? "Notificaciones"}
        className="flex h-10 w-10 items-center justify-center rounded-full text-on-surface-variant transition-colors hover:bg-surface-container-high active:scale-95"
      >
        <FilledBellIcon size={20} className="text-on-surface-variant" />
      </button>
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
  return (
    <Link
      to={to}
      aria-label={t(label)}
      title={t(label)}
      className={cn(
        "flex h-12 w-12 items-center justify-center rounded-full text-on-surface-variant transition-all hover:bg-surface-container-high active:scale-90",
        (matchEnd ? location.pathname === to : location.pathname.startsWith(to)) &&
          "bg-primary text-on-primary"
      )}
    >
      <Icon size={24} />
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