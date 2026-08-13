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
import { Input } from "@/components/ui/input";
import { Segmented } from "@/components/ui/segmented";
import { cn } from "@/lib/utils";
import { formatSymbol } from "@/lib/format";
import type { Category, Contact, Currency, Paginated, Wallet } from "@/lib/types";

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

const CURRENCIES = [
  { value: "USD", label: "USD" },
  { value: "VES", label: "VES" },
] as const;

function convertAmount(
  value: string,
  from: Currency,
  to: Currency,
  rate: number | null
): string {
  if (from === to || !rate || rate <= 0) return value;
  const num = Number(value);
  if (!Number.isFinite(num) || num <= 0) return value;
  const out = from === "USD" ? num * rate : num / rate;
  return String(Math.round(out * 100) / 100);
}

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
  const [dueDate, setDueDate] = useState("");
  const [reminderDays, setReminderDays] = useState("");
  const [done, setDone] = useState(false);
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
  const { data: rateData } = useQuery({
    queryKey: queryKeys.rates,
    queryFn: () => api.get<{ rate: string }>("/rates/current"),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  const rate = rateData?.rate ? Number(rateData.rate) : null;

  const changeCurrency = (c: Currency) => {
    if (c === currency) return;
    setMonto(convertAmount(monto, currency, c, rate));
    setCurrency(c);
  };

  const changeWallet = (id: string) => {
    setWallet(id);
    const w = (wallets ?? []).find((x) => x.id === id);
    if (w && w.currency !== currency) {
      setMonto(convertAmount(monto, currency, w.currency, rate));
      setCurrency(w.currency);
    }
  };

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
        estado: done ? "pagado" : "pendiente",
        remind_me: remindMe,
        fecha_vencimiento: remindMe && dueDate ? dueDate : undefined,
        reminder_days: remindMe ? (reminderDays === "" ? null : Number(reminderDays)) : undefined,
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
        <Segmented
          layoutId="seg-tipo"
          options={TX_TYPES.map(({ value, labelKey }) => ({
            value,
            label: t(labelKey),
          }))}
          value={tipo}
          onChange={setTipo}
        />

        {/* Amount + currency */}
        <section className="glass-panel-elevated clip-rounded-4xl relative flex min-h-[180px] flex-col items-center justify-center gap-7 overflow-hidden rounded-[2rem] px-6 py-10">
          <div className="pointer-events-none absolute top-1/2 left-1/2 h-36 w-36 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/5 blur-3xl" />
          <div className="relative z-10 w-full max-w-[260px]">
            <Segmented
              layoutId="seg-currency"
              size="lg"
              options={CURRENCIES.map((c) => ({ value: c.value, label: c.label }))}
              value={currency}
              onChange={changeCurrency}
            />
          </div>
          <div className="relative z-10 flex w-full items-baseline justify-center gap-2">
            <span className="text-4xl font-bold tracking-tight text-primary">
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
              className="w-full max-w-[280px] flex-1 bg-transparent text-center text-4xl font-bold tracking-tight text-on-surface outline-none focus:rounded-xl focus:bg-black/5"
            />
          </div>
        </section>

        {/* Details */}
        <section className="glass-panel clip-rounded-xl flex flex-col rounded-xl p-4">
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
              onChange={(e) => changeWallet(e.target.value)}
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
        <section className="glass-panel clip-rounded-xl flex flex-col rounded-xl p-4">
          <div className="flex items-center justify-between">
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
          </div>

          {remindMe && (
            <div className="mt-4 space-y-4 border-t border-glass-border pt-4">
              <div className="flex items-center gap-4">
                <label
                  htmlFor="tx-due"
                  className="w-28 shrink-0 text-sm font-medium text-on-surface"
                >
                  {t("addOperation.dueDate")}
                </label>
                <Input
                  id="tx-due"
                  type="date"
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                  className="flex-1"
                />
              </div>
              <div className="flex items-center gap-4">
                <label
                  htmlFor="tx-remind-days"
                  className="w-28 shrink-0 text-sm font-medium text-on-surface"
                >
                  {t("addOperation.reminderDays")}
                </label>
                <select
                  id="tx-remind-days"
                  value={reminderDays}
                  onChange={(e) => setReminderDays(e.target.value)}
                  className="h-11 w-full min-w-0 flex-1 rounded-xl border border-glass-border bg-glass-surface px-3 text-base text-on-surface shadow-sm outline-none transition-colors backdrop-blur-md focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 md:text-sm"
                >
                  <option value="">{t("addOperation.daysBeforeGlobal")}</option>
                  <option value="0">{t("addOperation.sameDay")}</option>
                  <option value="1">{t("addOperation.dayBeforeCount", { count: 1 })}</option>
                  {[2, 3, 4, 5, 7, 10, 14].map((n) => (
                    <option key={n} value={n}>
                      {t("addOperation.dayBeforeCount", { count: n })}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}
        </section>

        {/* Ya realizado */}
        <section className="glass-panel clip-rounded-xl flex items-center justify-between rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-status-paid/20">
              <CheckCircle2 className="h-4 w-4 text-status-paid" />
            </div>
            <div>
              <p className="text-sm font-medium text-on-surface">{t("addOperation.markAsDone")}</p>
              <p className="text-xs text-on-surface-variant">{t("addOperation.markAsDoneHint")}</p>
            </div>
          </div>
          <Switch checked={done} onCheckedChange={setDone} />
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
              if (!wallet) {
                setError(t("addOperation.walletRequired"));
                return;
              }
              create.mutate();
            }}
            disabled={create.isPending || !monto || !wallet}
          >
            <CheckCircle2 />
            {create.isPending ? t("common.loading") : t("addOperation.register")}
          </Button>
        </div>
      </footer>
    </div>
  );
}