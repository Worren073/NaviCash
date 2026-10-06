import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Briefcase, Check, ChevronLeft, Coins, Rocket } from "lucide-react";

import { api, ApiErrorClass } from "@/lib/api";
import { useMe, queryKeys } from "@/hooks/use-queries";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NumericInput } from "@/components/ui/numeric-input";
import { cn } from "@/lib/utils";
import { formatSymbol } from "@/lib/format";
import { sileo } from "sileo";
import type { Currency } from "@/lib/types";

const CURRENCIES: Array<{ value: Currency; label: string }> = [
  { value: "USD", label: "USD — Dólar" },
  { value: "VES", label: "VES — Bolívar" },
];

const STEPS = [
  { key: "step1", icon: Briefcase },
  { key: "step2", icon: Coins },
  { key: "step3", icon: Rocket },
] as const;

export function BusinessOnboarding() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: me } = useMe();

  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState<Currency>(me?.base_currency ?? "USD");
  const [capital, setCapital] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      api.post<{ id: string }>("/business", {
        name,
        currency,
        initial_capital: capital === "" ? 0 : capital,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.business });
      void queryClient.invalidateQueries({ queryKey: queryKeys.businessSummary });
      sileo.success({ title: t("business.created") });
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) setError(err.message);
      else setError(t("errors.generic"));
    },
  });

  const canNext =
    step === 0
      ? name.trim().length > 0
      : step === 1
        ? capital === "" || Number(capital) >= 0
        : true;

  const goNext = () => {
    setError(null);
    if (step === 0 && name.trim().length === 0) {
      setError(t("business.onboarding.errorName"));
      return;
    }
    if (step === 1 && capital !== "" && Number(capital) < 0) {
      setError(t("business.onboarding.errorCapital"));
      return;
    }
    if (step < 2) setStep(step + 1);
    else create.mutate();
  };

  return (
    <div className="flex min-h-[calc(100vh-10rem)] w-full items-center justify-center px-4 py-8 sm:min-h-[calc(100vh-8rem)]">
      <div className="mx-auto w-full max-w-md space-y-6 sm:max-w-xl md:max-w-2xl">
        {/* Header */}
        <div className="flex flex-col items-center gap-4 text-center sm:flex-row sm:items-start sm:text-left">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-primary/10 sm:h-14 sm:w-14">
            <Briefcase className="h-6 w-6 text-primary sm:h-7 sm:w-7" />
          </div>
          <div className="space-y-1">
            <h2 className="text-2xl font-bold text-on-surface sm:text-3xl">
              {t("business.onboarding.title")}
            </h2>
            <p className="max-w-lg text-sm text-on-surface-variant sm:text-base">
              {t("business.onboarding.intro")}
            </p>
          </div>
        </div>

        {/* Stepper */}
        <ol className="mx-auto flex w-full max-w-sm items-center gap-2 sm:max-w-md md:max-w-lg">
          {STEPS.map(({ key, icon: Icon }, i) => (
            <li key={key} className="flex flex-1 items-center gap-2">
              <span
                className={cn(
                  "flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm transition-colors sm:h-10 sm:w-10",
                  i < step
                    ? "bg-primary text-on-primary"
                    : i === step
                      ? "bg-primary/15 text-primary"
                      : "bg-surface-container-high text-on-surface-variant"
                )}
              >
                {i < step ? <Check className="h-4 w-4 sm:h-5 sm:w-5" /> : <Icon className="h-4 w-4 sm:h-5 sm:w-5" />}
              </span>
              {i < STEPS.length - 1 && (
                <span
                  className={cn(
                    "h-0.5 min-w-[1.5rem] flex-1 rounded-full",
                    i < step ? "bg-primary" : "bg-surface-container-high"
                  )}
                />
              )}
            </li>
          ))}
        </ol>

        {/* Card */}
        <div className="glass-panel clip-rounded-xl space-y-6 rounded-xl p-5 sm:p-8 md:p-10">
          {step === 0 && (
            <div className="space-y-5 sm:space-y-6">
              <div className="text-center sm:text-left">
                <h3 className="text-lg font-semibold text-on-surface sm:text-xl">
                  {t("business.onboarding.step1Title")}
                </h3>
                <p className="text-sm text-on-surface-variant sm:text-base">
                  {t("business.onboarding.step1Hint")}
                </p>
              </div>
              <div className="grid gap-4 sm:gap-5">
                <label className="block">
                  <span className="mb-1.5 block text-sm font-medium text-on-surface">
                    {t("business.onboarding.name")}
                  </span>
                  <Input
                    autoFocus
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder={t("business.onboarding.namePlaceholder")}
                    maxLength={80}
                  />
                </label>
                <label className="block">
                  <span className="mb-1.5 block text-sm font-medium text-on-surface">
                    {t("business.onboarding.currency")}
                  </span>
                  <select
                    value={currency}
                    onChange={(e) => setCurrency(e.target.value as Currency)}
                    className="h-11 w-full rounded-xl border border-glass-border bg-glass-surface px-3 text-base text-on-surface shadow-sm outline-none transition-colors backdrop-blur-md focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 md:text-sm"
                  >
                    {CURRENCIES.map((c) => (
                      <option key={c.value} value={c.value}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </div>
          )}

          {step === 1 && (
            <div className="space-y-5 sm:space-y-6">
              <div className="text-center sm:text-left">
                <h3 className="text-lg font-semibold text-on-surface sm:text-xl">
                  {t("business.onboarding.step2Title")}
                </h3>
                <p className="text-sm text-on-surface-variant sm:text-base">
                  {t("business.onboarding.step2Hint")}
                </p>
              </div>
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium text-on-surface">
                  {t("business.onboarding.initialCapital")}
                </span>
                <div className="flex items-center gap-3">
                  <span className="text-2xl font-bold text-primary sm:text-3xl">
                    {formatSymbol(currency)}
                  </span>
                  <NumericInput
                    placeholder="0.00"
                    value={capital}
                    onChange={setCapital}
                  />
                </div>
                <span className="mt-1.5 block text-xs text-on-surface-variant sm:text-sm">
                  {t("business.onboarding.initialCapitalHint")}
                </span>
              </label>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-5 sm:space-y-6">
              <div className="text-center sm:text-left">
                <h3 className="text-lg font-semibold text-on-surface sm:text-xl">
                  {t("business.onboarding.step3Title")}
                </h3>
                <p className="text-sm text-on-surface-variant sm:text-base">
                  {t("business.onboarding.step3Hint")}
                </p>
              </div>
              <dl className="mx-auto max-w-md space-y-3 rounded-xl bg-surface-container p-4 text-sm sm:p-5 sm:text-base">
                <div className="flex justify-between gap-3">
                  <dt className="text-on-surface-variant">{t("business.onboarding.name")}</dt>
                  <dd className="text-right font-semibold text-on-surface">{name}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-on-surface-variant">{t("business.onboarding.currency")}</dt>
                  <dd className="text-right font-semibold text-on-surface">{currency}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-on-surface-variant">{t("business.onboarding.initialCapital")}</dt>
                  <dd className="text-right font-semibold text-on-surface">
                    {formatSymbol(currency)}{" "}
                    {Number(capital || 0).toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </dd>
                </div>
              </dl>
            </div>
          )}

          {error && (
            <p className="rounded-lg bg-error-container/60 px-3 py-2 text-center text-sm text-on-error-container sm:text-base">
              {error}
            </p>
          )}
        </div>

        {/* Actions */}
        <div className="flex flex-col-reverse items-stretch justify-between gap-3 sm:flex-row sm:items-center">
          <Button
            variant="ghost"
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={step === 0 || create.isPending}
            className="gap-1"
          >
            <ChevronLeft className="h-4 w-4" />
            {t("common.back")}
          </Button>
          <Button
            variant="glow"
            onClick={goNext}
            disabled={!canNext || create.isPending}
            className="w-full sm:w-auto sm:min-w-[12rem]"
          >
            {step < 2
              ? t("common.next")
              : create.isPending
                ? t("business.onboarding.creating")
                : t("business.onboarding.create")}
          </Button>
        </div>
      </div>
    </div>
  );
}
