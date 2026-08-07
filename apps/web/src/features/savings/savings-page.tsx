import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link2, Plus, Trash2, Wallet2 } from "lucide-react";
import { TargetIcon } from "@/components/icons";

import { useOverview, useWallets, queryKeys } from "@/hooks/use-queries";
import { api, ApiErrorClass } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { BlurLoading } from "@/components/ui/blur-loading";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatMoney } from "@/lib/format";
import { NewWalletDialog, EditWalletDialog } from "@/features/wallets/wallets-page";
import { CardGlow } from "@/components/ui/card-glow";
import { ConfirmDeleteDialog } from "@/components/ui/confirm-delete-dialog";
import type { Paginated, SavingsGoal, Wallet } from "@/lib/types";

function LinkAccountsDialog({
  goal,
  savingWallets,
}: {
  goal: SavingsGoal;
  savingWallets: Array<Wallet>;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const selected = new Set(goal.linked_accounts.map((a) => a.id));

  const update = useMutation({
    mutationFn: (ids: string[]) =>
      api.patch<SavingsGoal>(`/savings/${goal.id}`, { linked_account_ids: ids }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.savings });
      setOpen(false);
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) void err;
    },
  });

  function toggle(id: string) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    update.mutate(Array.from(next));
  }

  return (
    <>
      <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
        <Link2 className="h-4 w-4" /> {t("savings.linkAccounts")}
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("savings.linkAccounts")}</DialogTitle>
            <DialogDescription>{t("savings.selectAccounts")}</DialogDescription>
          </DialogHeader>

          {savingWallets.length === 0 ? (
            <p className="rounded-lg bg-surface-container-high px-3 py-4 text-sm text-on-surface-variant">
              {t("savings.noSavingAccounts")}
            </p>
          ) : (
            <div className="space-y-2">
              {savingWallets.map((w) => {
                const checked = goal.linked_accounts.some((a) => a.id === w.id);
                return (
                  <label
                    key={w.id}
                    className="flex cursor-pointer items-center justify-between gap-3 rounded-xl border border-glass-border bg-glass-surface px-4 py-3 transition-colors hover:bg-surface-container-high"
                  >
                    <span className="flex items-center gap-3">
                      <span className="h-9 w-9 rounded-full" style={{ backgroundColor: w.color }} />
                      <span>
                        <span className="block text-sm font-medium text-on-surface">{w.name}</span>
                        <span className="block text-xs text-on-surface-variant">
                          {formatMoney(w.saldo, w.currency, { symbol: true })}
                        </span>
                      </span>
                    </span>
                    <span
                      role="checkbox"
                      aria-checked={checked}
                      tabIndex={0}
                      onClick={(e) => {
                        e.preventDefault();
                        toggle(w.id);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          toggle(w.id);
                        }
                      }}
                      className={`flex h-6 w-6 items-center justify-center rounded-md border-2 transition-colors ${
                        checked
                          ? "border-primary bg-primary text-on-primary"
                          : "border-on-surface-variant text-transparent"
                      }`}
                    >
                      <Plus className="h-4 w-4 rotate-45" />
                    </span>
                  </label>
                );
              })}
            </div>
          )}

          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              {t("common.close")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function GoalCard({
  goal,
  savingWallets,
}: {
  goal: SavingsGoal;
  savingWallets: Array<Wallet>;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [confirmOpen, setConfirmOpen] = useState(false);

  const remove = useMutation({
    mutationFn: () => api.delete(`/savings/${goal.id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.savings });
      setConfirmOpen(false);
    },
  });

  const pct = Number(goal.progress_percent);

  return (
    <div className="glass-card relative overflow-hidden rounded-xl bg-surface p-4">
      <CardGlow color="#006a61" />
      <div className="relative mb-3">
        <h3 className="text-lg font-semibold text-on-surface">{goal.name}</h3>
      </div>
      <div className="relative mb-3 flex items-center gap-1.5">
        <button
          type="button"
          aria-label={t("common.delete")}
          onClick={() => setConfirmOpen(true)}
          className="rounded-full p-1.5 text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-status-delayed"
        >
          <Trash2 className="h-4 w-4" />
        </button>
        <LinkAccountsDialog goal={goal} savingWallets={savingWallets} />
      </div>

      <div className="relative mb-2 flex items-end justify-between">
        <span className="text-xl font-bold text-on-surface">
          {formatMoney(goal.total_contributed, goal.currency, { symbol: true })}
        </span>
        <span className="text-sm text-on-surface-variant">
          {t("savings.progress", { percent: pct.toFixed(1) })}
        </span>
      </div>

      <div className="relative h-2.5 overflow-hidden rounded-full bg-surface-container-highest">
        <div
          className="h-full rounded-full bg-primary transition-all"
          style={{
            width: `${Math.min(100, pct)}%`,
            boxShadow: "0 0 8px rgba(0,106,97,0.4)",
          }}
        />
      </div>

      <div className="relative mt-2 flex items-center justify-between text-sm">
        <span className="text-on-surface-variant">{t("savings.goalTotal")}</span>
        <span className="font-semibold text-on-surface">
          {formatMoney(goal.target_amount, goal.currency, { symbol: true })}
        </span>
      </div>

      <div className="relative mt-3">
        {goal.linked_accounts.length === 0 ? (
          <p className="text-xs text-on-surface-variant">{t("savings.linkedEmpty")}</p>
        ) : (
          <>
            <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-on-surface-variant">
              {goal.linked_accounts.length === 1
                ? t("savings.linkedAccounts")
                : t("savings.linkedAccountsPlural")}
            </p>
            <div className="space-y-1.5">
              {goal.linked_accounts.map((acc) => (
                <div
                  key={acc.id}
                  className="flex items-center justify-between rounded-lg bg-surface-container-low px-3 py-1.5 text-sm"
                >
                  <span className="text-on-surface">{acc.name}</span>
                  <span className="font-medium text-on-surface">
                    {formatMoney(acc.saldo, acc.currency, { symbol: true })}
                  </span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      <ConfirmDeleteDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        itemName={t("savings.item")}
        itemLabel={goal.name}
        pending={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
    </div>
  );
}

export default function SavingsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [target, setTarget] = useState("");
  const [goalAccounts, setGoalAccounts] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const { data: overview } = useOverview();
  const { data: wallets, isLoading: walletsLoading } = useWallets();

  const { data, isLoading, isError } = useQuery({
    queryKey: queryKeys.savings,
    queryFn: () => api.get<Paginated<SavingsGoal>>("/savings").then((d) => d.results),
  });

  const create = useMutation({
    mutationFn: () =>
      api.post<SavingsGoal>("/savings", {
        name,
        target_amount: target,
        ...(goalAccounts.length === 0 ? { currency: "USD" } : {}),
        linked_account_ids: goalAccounts,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.savings });
      setOpen(false);
      setName("");
      setTarget("");
      setGoalAccounts([]);
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) setError(err.message);
      else setError(t("errors.generic"));
    },
  });

  // Cuentas de ahorro (tipo "saving") con su valor en USD desde el overview.
  const savingWallets = (wallets ?? []).filter((w) => w.tipo === "saving");
  const usdValues = new Map<string, string>(
    (overview?.wallets ?? []).map((w) => [w.id, w.usd_value])
  );
const accountsUsd = savingWallets.reduce(
    (acc, w) => acc + Number(usdValues.get(w.id) ?? w.saldo),
    0
  );
  // Las metas NO modifican el total de ahorros: el total es solo la suma del
  // saldo de las billeteras de ahorro. Las metas son una herramienta de
  // seguimiento, no suman dinero extra.
  const totalSavedUsd = accountsUsd;

  return (
    <div className="mt-4 space-y-6">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
            <TargetIcon size={20} className="text-primary" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-on-surface">{t("savings.title")}</h2>
            <p className="text-sm text-on-surface-variant">{t("savings.subtitle")}</p>
          </div>
        </div>
        <Button variant="glow" onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" /> {t("savings.newGoal")}
        </Button>
      </div>

      {/* Dashboard: total ahorrado */}
      <BlurLoading loading={isLoading || walletsLoading}>
        <div className="glass-card relative overflow-hidden rounded-xl bg-surface-container-low p-6">
          <CardGlow color="#006a61" />
          <p className="relative mb-1 text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
            {t("savings.totalSaved")}
          </p>
          <div className="relative flex items-end gap-2">
            <span className="text-4xl font-bold tracking-tight text-on-surface">
              {formatMoney(totalSavedUsd, "USD", { symbol: true })}
            </span>
          </div>
          <div className="relative mt-4 flex gap-2">
            <span className="rounded-full bg-surface-container-high px-3 py-1 text-xs font-medium text-on-surface-variant">
              {t("savings.countAccounts", { count: savingWallets.length })}
            </span>
            <span className="rounded-full bg-surface-container-high px-3 py-1 text-xs font-medium text-on-surface-variant">
              {t("savings.countGoals", { count: (data ?? []).length })}
            </span>
          </div>
        </div>
      </BlurLoading>

      {/* Cuentas de ahorro */}
      <section className="space-y-2">
        <h3 className="text-lg font-semibold text-on-surface">{t("savings.accounts")}</h3>
        {walletsLoading ? (
          <>
            <Skeleton className="h-28 w-full" />
            <Skeleton className="h-28 w-full" />
          </>
        ) : savingWallets.length === 0 ? (
          <p className="glass-panel rounded-lg p-6 text-center text-sm text-on-surface-variant">
            {t("savings.noAccounts")}
          </p>
        ) : (
          savingWallets.map((wallet) => (
            <EditWalletDialog
              key={wallet.id}
              wallet={wallet}
              usdValue={usdValues.get(wallet.id) ?? wallet.saldo}
            />
          ))
        )}
        <NewWalletDialog defaultTipo="saving" />
      </section>

      {/* Metas de ahorro */}
      <section className="space-y-2">
        <h3 className="text-lg font-semibold text-on-surface">{t("savings.goals")}</h3>
        <BlurLoading loading={isLoading}>
          {isError ? (
            <p className="glass-panel rounded-lg p-6 text-center text-sm text-on-surface-variant">
              {t("errors.generic")}
            </p>
          ) : isLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : (data ?? []).length === 0 ? (
            <p className="glass-panel rounded-lg p-6 text-center text-sm text-on-surface-variant">
              {t("savings.empty")}
            </p>
          ) : (
            <div className="space-y-2">
              {(data ?? []).map((goal) => (
                <GoalCard key={goal.id} goal={goal} savingWallets={savingWallets} />
              ))}
            </div>
          )}
        </BlurLoading>
      </section>

      {/* Create goal dialog */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("savings.newGoal")}</DialogTitle>
            <DialogDescription>
              <Wallet2 className="mr-1 inline h-4 w-4 text-primary" />
              {t("savings.subtitle")}
            </DialogDescription>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              setError(null);
              create.mutate();
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="goal-name">{t("savings.goalName")}</Label>
              <Input
                id="goal-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="goal-target">{t("savings.targetAmount")}</Label>
              <Input
                id="goal-target"
                type="number"
                step="0.01"
                min="0.01"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label>{t("savings.linkAccounts")}</Label>
              {savingWallets.length === 0 ? (
                <p className="rounded-lg bg-surface-container-high px-3 py-3 text-sm text-on-surface-variant">
                  {t("savings.noSavingAccounts")}
                </p>
              ) : (
                <div className="max-h-44 space-y-1.5 overflow-y-auto pr-1">
                  {savingWallets.map((w) => {
                    const checked = goalAccounts.includes(w.id);
                    return (
                      <label
                        key={w.id}
                        className="flex cursor-pointer items-center justify-between gap-3 rounded-xl border border-glass-border bg-glass-surface px-4 py-2.5 transition-colors hover:bg-surface-container-high"
                      >
                        <span className="flex items-center gap-2.5">
                          <span className="h-6 w-6 rounded-full" style={{ backgroundColor: w.color }} />
                          <span className="text-sm text-on-surface">{w.name}</span>
                        </span>
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() =>
                            setGoalAccounts((prev) =>
                              checked ? prev.filter((id) => id !== w.id) : [...prev, w.id]
                            )
                          }
                          className="h-4 w-4 accent-primary"
                        />
                      </label>
                    );
                  })}
                </div>
              )}
            </div>

            {error && (
              <p className="rounded-lg bg-error-container/60 px-3 py-2 text-sm text-on-error-container">
                {error}
              </p>
            )}
            <DialogFooter>
              <Button type="submit" disabled={create.isPending}>
                {create.isPending ? t("common.loading") : t("common.save")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}