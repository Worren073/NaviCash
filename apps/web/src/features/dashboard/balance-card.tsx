import { useTranslation } from "react-i18next";
import { Skeleton } from "@/components/ui/skeleton";
import { BlurLoading } from "@/components/ui/blur-loading";
import { CurrencyDollarIcon } from "@/components/icons";

interface BalanceCardProps {
  label: string;
  symbol: string;
  amount: string | null;
  isLoading: boolean;
  equivalentLabel?: string;
  equivalentValue?: string | null;
  tone?: "default" | "flag" | "green";
  showRate?: boolean;
  rate?: string | null;
}

/**
 * Tarjeta de balance con cristal esmerilado, brillo y equivalente.
 * Compartida entre el dashboard y la vista de billeteras.
 */
export function BalanceCard({
  label,
  symbol,
  amount,
  isLoading,
  equivalentLabel,
  equivalentValue,
  tone = "default",
  showRate,
  rate,
}: BalanceCardProps) {
  const { t } = useTranslation();
  const glow =
    tone === "flag"
      ? [
          "bg-yellow-400/40",
          "bg-blue-500/40",
          "bg-yellow-400/30",
          "bg-red-500/40",
          "bg-blue-500/30",
          "bg-red-500/20",
        ]
      : tone === "green"
        ? [
            "bg-emerald-400/40",
            "bg-green-500/40",
            "bg-emerald-400/30",
            "bg-green-500/30",
            "bg-emerald-400/20",
            "bg-green-500/20",
          ]
        : [
            "bg-sky-400/40",
            "bg-primary/40",
            "bg-sky-400/30",
            "bg-primary/30",
            "bg-sky-400/15",
            "bg-primary/30",
          ];
  return (
    <section className="glass-panel clip-rounded-xl relative w-[85%] shrink-0 snap-center overflow-hidden rounded-xl p-6">
      <div
        className={`absolute inset-0 opacity-50 ${
          tone === "flag"
            ? "bg-gradient-to-br from-yellow-400/20 via-blue-500/15 to-red-500/20"
            : tone === "green"
              ? "bg-gradient-to-br from-emerald-400/15 to-transparent"
              : "bg-gradient-to-br from-primary/10 to-transparent"
        }`}
      />
      <div className={`pointer-events-none absolute -left-10 -top-10 h-28 w-28 rounded-full blur-2xl ${glow[0]}`} />
      <div className={`pointer-events-none absolute -left-2 -top-6 h-16 w-16 rounded-full blur-xl ${glow[1]}`} />
      <div className={`pointer-events-none absolute -right-10 -bottom-10 h-28 w-28 rounded-full blur-2xl ${glow[2]}`} />
      <div className={`pointer-events-none absolute -right-2 -bottom-6 h-16 w-16 rounded-full blur-xl ${glow[3]}`} />
      <div className={`pointer-events-none absolute left-1/2 top-1/2 h-16 w-40 -translate-x-1/2 -translate-y-1/2 rounded-full blur-2xl ${glow[4]}`} />
      <BlurLoading loading={isLoading}>
        <div className="relative z-10 flex flex-col items-center space-y-2 text-center">
          <span className="text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
            {label}
          </span>
          {isLoading ? (
            <Skeleton className="h-11 w-44" />
          ) : (
            <div className="flex items-baseline gap-1">
              <span className="text-2xl font-semibold text-primary">{symbol}</span>
              <span className="text-4xl font-bold tracking-tight text-on-surface">
                {amount ?? "0.00"}
              </span>
            </div>
          )}
          {equivalentValue != null && (
            <div className="glass-panel clip-rounded-2xl mt-2 flex items-center gap-2 rounded-2xl px-4 py-1.5">
              <span className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
                {equivalentLabel}
              </span>
              <span className="text-sm font-bold text-on-surface">
                {equivalentValue}
              </span>
            </div>
          )}
          {showRate && rate != null && (
            <>
              <div className="my-0.5 h-px w-24 bg-glass-border" />
              <div className="glass-panel clip-rounded-2xl flex items-center gap-2 rounded-2xl px-4 py-1.5">
                <CurrencyDollarIcon size={16} className="text-primary" />
                <span className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
                  {t("dashboard.bcvRate", {
                    rate: Number(rate).toFixed(2),
                  })}
                </span>
              </div>
            </>
          )}
        </div>
      </BlurLoading>
    </section>
  );
}
