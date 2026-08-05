// Formateo es-VE: montos y fechas adaptados a la zona del usuario.

export function formatMoney(
  amount: number | string,
  currency: string = "USD",
  opts: { symbol?: boolean } = {}
): string {
  const num = typeof amount === "string" ? Number(amount) : amount;
  if (!Number.isFinite(num)) return "—";

  const locale = "es-VE";
  const formatted = new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num);

  if (!opts.symbol) return formatted;

  const symbol = currency === "USD" ? "USD" : "Bs";
  const sign = num < 0 ? "-" : "";
  return `${sign}${symbol} ${formatted.replace("-", "")}`;
}

/** Formato compacto para tarjetas bento (p. ej. $3,200). */
export function formatCompact(amount: number | string, currency: string = "USD"): string {
  const num = typeof amount === "string" ? Number(amount) : amount;
  if (!Number.isFinite(num)) return "—";
  const symbol = currency === "USD" ? "$" : "Bs";
  return `${symbol}${new Intl.NumberFormat("es-VE", {
    maximumFractionDigits: num % 1 === 0 ? 0 : 2,
  }).format(num)}`;
}

export function formatSymbol(currency: string): string {
  return currency === "USD" ? "$" : "Bs.";
}

export function formatDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  return new Intl.DateTimeFormat("es-VE", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

/** "Today, 10:45 AM" -> fecha relativa corta para listas de actividad. */
export function formatRelativeEvent(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diffDays = Math.round((startToday.getTime() - startDay.getTime()) / 86_400_000);

  if (diffDays === 0) {
    return new Intl.DateTimeFormat("es-VE", {
      hour: "2-digit",
      minute: "2-digit",
    }).format(d);
  }
  if (diffDays === 1) return "Ayer";
  return new Intl.DateTimeFormat("es-VE", { month: "short", day: "numeric" }).format(d);
}