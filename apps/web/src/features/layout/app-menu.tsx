import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CalendarRange, PiggyBank } from "lucide-react";

import { GlassPopover } from "@/components/ui/glass-popover";

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
  return (
    <GlassPopover open={open} onClose={onClose} className="w-60 bg-white/90 backdrop-blur-[60px]">
      <div className="p-2">
        <p className="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-on-surface-variant">
          {t("menu.title")}
        </p>
        <MenuLink to="/savings" onNavigate={onClose} label={t("menu.savings")} icon={<PiggyBank className="h-5 w-5 text-emerald-500" />} />
        <MenuLink to="/subscriptions" onNavigate={onClose} label={t("menu.subscriptions")} icon={<CalendarRange className="h-5 w-5 text-primary" />} />
      </div>
    </GlassPopover>
  );
}