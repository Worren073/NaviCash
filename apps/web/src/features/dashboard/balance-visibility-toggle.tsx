import { AnimatePresence, motion } from "motion/react";
import { Eye, EyeOff } from "lucide-react";
import { useTranslation } from "react-i18next";

interface BalanceVisibilityToggleProps {
  hidden: boolean;
  onToggle: () => void;
}

/**
 * Botón de ojo que oculta/muestra los montos del balance.
 * Alterna Eye ⇄ EyeOff con crossfade animado.
 */
export function BalanceVisibilityToggle({ hidden, onToggle }: BalanceVisibilityToggleProps) {
  const { t } = useTranslation();
  const label = hidden ? t("common.showBalances") : t("common.hideBalances");
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={hidden}
      aria-label={label}
      title={label}
      className="glass-panel clip-rounded-lg relative flex h-9 w-9 items-center justify-center rounded-lg text-on-surface-variant transition-colors hover:text-on-surface active:scale-95"
    >
      <AnimatePresence mode="wait" initial={false}>
        {hidden ? (
          <motion.span
            key="off"
            initial={{ opacity: 0, scale: 0.6, rotate: -40 }}
            animate={{ opacity: 1, scale: 1, rotate: 0 }}
            exit={{ opacity: 0, scale: 0.6, rotate: 40 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="flex"
          >
            <EyeOff size={18} />
          </motion.span>
        ) : (
          <motion.span
            key="on"
            initial={{ opacity: 0, scale: 0.6, rotate: -40 }}
            animate={{ opacity: 1, scale: 1, rotate: 0 }}
            exit={{ opacity: 0, scale: 0.6, rotate: 40 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="flex"
          >
            <Eye size={18} />
          </motion.span>
        )}
      </AnimatePresence>
    </button>
  );
}
