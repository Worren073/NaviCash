import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  BellRing,
  CheckCircle2,
  ContactRound,
  PenLine,
  Tag,
  type LucideIcon,
} from "lucide-react";

import { api, ApiErrorClass } from "@/lib/api";
import { queryKeys } from "@/hooks/use-queries";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { formatSymbol } from "@/lib/format";
import type { Category, Contact, Paginated, Wallet } from "@/lib/types";

const CATEGORY_ICONS: Record<string, LucideIcon> = {
  restaurant: Tag,
  directions_car: Tag,
  shopping_bag: Tag,
  tag: Tag,
};

const TX_TYPES = [
  { value: "cobro", labelKey: "addOperation.typeCobro" },
  { value: "pago", labelKey: "addOperation.typePago" },
] as const;

export default function NewOperationPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [tipo, setTipo] = useState<"cobro" | "pago">("pago");
  const [currency, setCurrency] = useState<"USD" | "VES">("USD");
  const [monto, setMonto] = useState("");
  const [concepto, setConcepto] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [contact, setContact] = useState<string>("");
  const [wallet, setWallet] = useState<string>("");
  const [remindMe, setRemindMe] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: categories } = useQuery({
    queryKey: queryKeys.categories,
    queryFn: () =>
      api.get<Paginated<Category>>("/categories").then((d) => d.results),
  });
  const { data: contacts } = useQuery({
    queryKey: queryKeys.contacts,
    queryFn: () =>
      api.get<Paginated<Contact>>("/contacts").then((d) => d.results),
  });
  const { data: wallets } = useQuery({
    queryKey: queryKeys.wallets,
    queryFn: () => api.get<Paginated<Wallet>>("/wallets").then((d) => d.results),
  });

  const create = useMutation({
    mutationFn: () =>
      api.post<{ id: string }>("/transactions", {
        tipo,
        monto,
        moneda: currency,
        concepto: concepto || undefined,
        category: category ?? undefined,
        contact: contact || undefined,
        wallet: wallet || undefined,
        remind_me: remindMe,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.transactions });
      void queryClient.invalidateQueries({ queryKey: queryKeys.overview });
      navigate("/");
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) setError(err.message);
      else setError(t("errors.generic"));
    },
  });

  const visibleCats = (categories ?? []).slice(0, 6);

  return (
    <div className="fixed inset-0 z-40 flex h-full w-full flex-col bg-surface/95 backdrop-blur-3xl">
      {/* Header */}
      <header className="flex w-full shrink-0 items-center justify-between px-5 py-4">
        <button
          type="button"
          aria-label={t("common.close")}
          onClick={() => navigate(-1)}
          className="rounded-full p-2 -ml-2 text-on-surface-variant transition-colors hover:text-on-surface active:bg-black/5"
        >
          <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6 6 18M6 6l12 12" strokeLinecap="round" />
          </svg>
        </button>
        <h1 className="absolute left-1/2 -translate-x-1/2 text-xl font-semibold tracking-tight text-on-surface">
          {t("addOperation.title")}
        </h1>
        <div className="w-10" />
      </header>

      {/* Scrollable form */}
      <div className="flex flex-1 flex-col gap-6 overflow-y-auto px-5 pb-32 pt-2">
        {/* Tipo cobro/pago */}
        <section className="flex rounded-full border border-glass-border bg-surface-container-highest p-1">
          {TX_TYPES.map(({ value, labelKey }) => (
            <button
              key={value}
              type="button"
              onClick={() => setTipo(value)}
              className={cn(
                "flex-1 rounded-full px-4 py-2 text-sm font-medium transition-all",
                tipo === value
                  ? "bg-primary text-white shadow-[0_2px_8px_rgba(0,106,97,0.2)]"
                  : "text-on-surface-variant"
              )}
            >
              {t(labelKey)}
            </button>
          ))}
        </section>

        {/* Amount + currency */}
        <section className="glass-panel-elevated relative flex flex-col items-center justify-center gap-5 overflow-hidden rounded-[2rem] p-8">
          <div className="pointer-events-none absolute top-1/2 left-1/2 h-32 w-32 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/5 blur-3xl" />
          <div className="relative z-10 flex rounded-full border border-glass-border bg-surface-container-highest p-1">
            {(["USD", "VES"] as const).map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setCurrency(c)}
                className={cn(
                  "rounded-full px-6 py-2 text-sm font-medium transition-all",
                  currency === c
                    ? "bg-primary text-white shadow-[0_2px_8px_rgba(0,106,97,0.2)]"
                    : "text-on-surface-variant"
                )}
              >
                {c}
              </button>
            ))}
          </div>
          <div className="relative z-10 flex w-full items-baseline justify-center">
            <span className="mr-2 text-4xl font-bold tracking-tight text-primary">
              {formatSymbol(currency)}
            </span>
            <input
              autoFocus
              type="number"
              inputMode="decimal"
              step="0.01"
              min="0"
              placeholder="0.00"
              value={monto}
              onChange={(e) => setMonto(e.target.value)}
              aria-label={t("addOperation.amountLabel")}
              className="w-full max-w-[220px] bg-transparent text-center text-4xl font-bold tracking-tight text-on-surface outline-none focus:rounded-xl focus:bg-black/5"
            />
          </div>
        </section>

        {/* Details */}
        <section className="glass-panel flex flex-col rounded-xl p-4">
          {/* Concept */}
          <div className="flex items-center gap-4 border-b border-glass-border py-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-surface-container-high">
              <PenLine className="h-5 w-5 text-primary" />
            </div>
            <input
              type="text"
              value={concepto}
              onChange={(e) => setConcepto(e.target.value)}
              placeholder={t("addOperation.concept")}
              className="w-full bg-transparent text-base text-on-surface outline-none placeholder:text-on-surface-variant"
            />
          </div>

          {/* Wallet */}
          <div className="flex items-center gap-4 border-b border-glass-border py-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-surface-container-high">
              <Tag className="h-5 w-5 text-primary" />
            </div>
            <select
              value={wallet}
              onChange={(e) => setWallet(e.target.value)}
              aria-label={t("addOperation.wallet")}
              className="w-full bg-transparent text-base text-on-surface outline-none"
            >
              <option value="">{t("addOperation.wallet")}</option>
              {(wallets ?? []).map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name} · {w.currency}
                </option>
              ))}
            </select>
          </div>

          {/* Category chips */}
          <div className="flex items-center gap-4 border-b border-glass-border py-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-surface-container-high">
              <Tag className="h-5 w-5 text-primary" />
            </div>
            <div className="flex flex-1 gap-2 overflow-x-auto pb-1 snap-x scrollbar-hide">
              {visibleCats.map((cat) => {
                const Icon = CATEGORY_ICONS[cat.icon] ?? Tag;
                const active = category === cat.id;
                return (
                  <button
                    key={cat.id}
                    type="button"
                    onClick={() => setCategory(active ? null : cat.id)}
                    className={cn(
                      "flex shrink-0 snap-start items-center gap-2 rounded-full border px-4 py-2 text-xs font-semibold transition-all",
                      active
                        ? "border-primary/20 bg-primary/10 text-primary"
                        : "border-glass-border bg-surface-container text-on-surface-variant"
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    {cat.name}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Contact */}
          <div className="flex items-center gap-4 py-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-surface-container-high">
              <ContactRound className="h-5 w-5 text-primary" />
            </div>
            <select
              value={contact}
              onChange={(e) => setContact(e.target.value)}
              aria-label={t("addOperation.contact")}
              className="w-full bg-transparent text-base text-on-surface outline-none"
            >
              <option value="">{t("addOperation.contact")}</option>
              {(contacts ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        </section>

        {/* Remind me */}
        <section className="glass-panel flex items-center justify-between rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-container-high">
              <BellRing className="h-4 w-4 text-status-warning" />
            </div>
            <div>
              <p className="text-sm font-medium text-on-surface">{t("addOperation.remindMe")}</p>
              <p className="text-xs text-on-surface-variant">{t("addOperation.remindMeHint")}</p>
            </div>
          </div>
          <Switch checked={remindMe} onCheckedChange={setRemindMe} />
        </section>
      </div>

      {/* Fixed bottom action */}
      <footer className="fixed inset-x-0 bottom-0 bg-gradient-to-t from-surface via-surface/90 to-transparent pb-6 pt-12">
        <div className="px-5">
          {error && (
            <p className="mb-3 rounded-lg bg-error-container/60 px-3 py-2 text-sm text-on-error-container">
              {error}
            </p>
          )}
          <Button
            variant="glow"
            size="lg"
            className="w-full py-4 text-xl"
            onClick={() => {
              setError(null);
              create.mutate();
            }}
            disabled={create.isPending || !monto}
          >
            <CheckCircle2 />
            {create.isPending ? t("common.loading") : t("addOperation.register")}
          </Button>
        </div>
      </footer>
    </div>
  );
}