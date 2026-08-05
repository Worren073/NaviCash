import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Plus, Wallet2 } from "lucide-react";
import { TargetIcon } from "@/components/icons";

import { api, ApiErrorClass } from "@/lib/api";
import { queryKeys } from "@/hooks/use-queries";
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
import type { Paginated, SavingsGoal } from "@/lib/types";

function GoalCard({ goal }: { goal: SavingsGoal }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const contribute = useMutation({
    mutationFn: () =>
      api.post<{ detail: string }>(`/savings/${goal.id}/contributions`, {
        amount,
        currency: goal.currency,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.savings });
      setOpen(false);
      setAmount("");
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) setError(err.message);
      else setError(t("errors.generic"));
    },
  });

  const pct = Number(goal.progress_percent);

  return (
    <div className="glass-card rounded-xl bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-on-surface">{goal.name}</h3>
        <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" /> {t("savings.contribute")}
        </Button>
      </div>

      <div className="mb-2 flex items-end justify-between">
        <span className="text-xl font-bold text-on-surface">
          {formatMoney(goal.total_contributed, goal.currency, { symbol: true })}
        </span>
        <span className="text-sm text-on-surface-variant">
          {t("savings.progress", { percent: pct.toFixed(1) })}
        </span>
      </div>

      <div className="h-2.5 overflow-hidden rounded-full bg-surface-container-highest">
        <div
          className="h-full rounded-full bg-primary transition-all"
          style={{
            width: `${Math.min(100, pct)}%`,
            boxShadow: "0 0 8px rgba(0,106,97,0.4)",
          }}
        />
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("savings.contribute")}</DialogTitle>
            <DialogDescription>{goal.name}</DialogDescription>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              setError(null);
              contribute.mutate();
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor={`amount-${goal.id}`}>{t("savings.contributeAmount")}</Label>
              <Input
                id={`amount-${goal.id}`}
                type="number"
                step="0.01"
                min="0.01"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                required
              />
            </div>
            {error && (
              <p className="rounded-lg bg-error-container/60 px-3 py-2 text-sm text-on-error-container">
                {error}
              </p>
            )}
            <DialogFooter>
              <Button type="submit" disabled={contribute.isPending}>
                {contribute.isPending ? t("common.loading") : t("savings.contribute")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function SavingsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [target, setTarget] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: queryKeys.savings,
    queryFn: () => api.get<Paginated<SavingsGoal>>("/savings").then((d) => d.results),
  });

  const create = useMutation({
    mutationFn: () =>
      api.post<SavingsGoal>("/savings", {
        name,
        target_amount: target,
        currency: "USD",
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.savings });
      setOpen(false);
      setName("");
      setTarget("");
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) setError(err.message);
      else setError(t("errors.generic"));
    },
  });

  return (
    <div className="mt-4 space-y-4">
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
              <GoalCard key={goal.id} goal={goal} />
            ))}
          </div>
        )}
      </BlurLoading>

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