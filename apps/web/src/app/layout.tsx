import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
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
import { NaviBubble } from "@/features/assistant/navi-bubble";
import { AssistantChat } from "@/features/assistant/assistant-chat";
import { NaviVoice } from "@/features/assistant/navi-voice";
import { useNotifications } from "@/hooks/use-queries";
import { IOSLimitationsNotice } from "@/components/ios-limitations-notice";
import { DeviceInfo } from "@/components/device-info";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/", label: "nav.dashboard", icon: HomeIcon },
  { to: "/wallets", label: "nav.wallets", icon: WalletIcon },
] as const;

// Mantener presionado el "+" abre la voz de Navi (hold de 400 ms).
const HOLD_MS = 400;

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
    <header className="fixed inset-x-0 top-0 z-50 flex w-full items-center justify-between border-b border-glass-border bg-glass-surface/60 px-5 pt-[calc(env(safe-area-inset-top)+1rem)] pb-4 shadow-sm backdrop-blur-xl">
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

function AddButton({ onVoiceOpen }: { onVoiceOpen: () => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const holdTimer = useRef<number | null>(null);
  const held = useRef(false);

  function clearHold() {
    if (holdTimer.current !== null) {
      window.clearTimeout(holdTimer.current);
      holdTimer.current = null;
    }
  }

  function onPointerDown() {
    held.current = false;
    clearHold();
    // Mantener presionado → voz de Navi.
    holdTimer.current = window.setTimeout(() => {
      held.current = true;
      clearHold();
      onVoiceOpen();
    }, HOLD_MS);
  }

  function onClick(e: React.MouseEvent) {
    if (held.current) {
      e.preventDefault();
      held.current = false;
      return;
    }
    navigate("/operations/new");
  }

  return (
    <button
      type="button"
      aria-label={t("nav.add")}
      title={t("nav.add")}
      onPointerDown={onPointerDown}
      onPointerUp={clearHold}
      onPointerLeave={clearHold}
      onPointerCancel={clearHold}
      onContextMenu={(e) => e.preventDefault()}
      onClick={onClick}
      className="flex h-14 w-14 -translate-y-1.5 items-center justify-center rounded-full border-2 border-surface bg-primary text-white shadow-lg shadow-primary/30 transition-all hover:opacity-90 active:scale-90 select-none"
      style={{ touchAction: "none" }}
    >
      <Plus className="h-7 w-7" style={{ strokeWidth: 2.5 }} />
    </button>
  );
}

function BottomNav({ onVoiceOpen }: { onVoiceOpen: () => void }) {
  return (
    <nav
      aria-label="Navegación principal"
      className="clip-rounded-2xl fixed bottom-[calc(env(safe-area-inset-bottom)+0.5rem)] left-1/2 z-50 flex w-[calc(100%-2.5rem)] max-w-md -translate-x-1/2 items-center justify-around rounded-2xl border border-glass-border bg-glass-surface/60 p-2 shadow-[0_8px_32px_0_rgba(0,0,0,0.1)] backdrop-blur-2xl"
    >
      {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
        <NavLink key={to} to={to} label={label} icon={Icon} matchEnd={to === "/"} />
      ))}
      <AddButton onVoiceOpen={onVoiceOpen} />
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
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [voiceOpen, setVoiceOpen] = useState(false);
  return (
    <div className="min-h-dvh pb-[calc(env(safe-area-inset-bottom)+7rem)]">
      <TopBar />
      <main className="mx-auto w-full max-w-lg px-5 pb-8 pt-[calc(env(safe-area-inset-top)+3.5rem)]">
        <div key={location.pathname} className="view-enter">
          <Outlet />
        </div>
      </main>
      <NaviBubble onOpen={() => setAssistantOpen(true)} />
      <AssistantChat open={assistantOpen} onClose={() => setAssistantOpen(false)} />
      <NaviVoice open={voiceOpen} onClose={() => setVoiceOpen(false)} />
      <IOSLimitationsNotice />
      <DeviceInfo />
      <BottomNav onVoiceOpen={() => setVoiceOpen(true)} />
    </div>
  );
}
