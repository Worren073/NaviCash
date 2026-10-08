import { useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  LabelList,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertTriangle,
  Boxes,
  HandCoins,
  Percent,
  TrendingDown,
  TrendingUp,
  Wallet,
} from "lucide-react";

import { useBusinessAnalytics } from "@/hooks/use-queries";
import { useHideBalances } from "@/hooks/use-hide-balances";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Segmented } from "@/components/ui/segmented";
import { formatCompact, formatMoney } from "@/lib/format";
import type {
  BusinessAnalyticsCategory,
  BusinessAnalyticsPnlRow,
} from "@/lib/types";

const CATEGORY_COLORS = [
  "#7ed6ec",
  "#4ade80",
  "#fb7185",
  "#29a195",
  "#22d3ee",
  "#a78bfa",
  "#fbbf24",
  "#f472b6",
];

interface ChartTooltipProps {
  active?: boolean;
  label?: string | number;
  payload?: ReadonlyArray<{
    name?: string | number;
    value?: string | number;
    color?: string;
    dataKey?: string | number;
  }>;
  currency: string;
}

function ChartTooltip({ active, payload, label, currency }: ChartTooltipProps) {
  const { t } = useTranslation();
  if (!active || !payload?.length) return null;
  return (
    <div className="glass-panel clip-rounded-lg rounded-lg px-3 py-2 text-xs shadow-lg">
      <div className="mb-1.5 font-semibold text-on-surface">{label ?? ""}</div>
      {payload.map((entry, index) => (
        <div
          key={`${entry.dataKey ?? entry.name ?? index}`}
          className="flex items-center justify-between gap-4"
        >
          <span className="flex items-center gap-1.5 text-on-surface-variant">
            <span
              className="h-2 w-2 rounded-full"
              style={{ background: entry.color ?? CATEGORY_COLORS[index] }}
            />
            {entry.name ?? t("analytics.total")}
          </span>
          <span className="font-semibold text-on-surface">
            {formatMoney(Number(entry.value ?? 0), currency, { symbol: true })}
          </span>
        </div>
      ))}
    </div>
  );
}

function fmtMonth(ym: string): string {
  const d = new Date(`${ym}-01T12:00:00`);
  return Number.isNaN(d.getTime()) ? ym : d.toLocaleDateString("es-VE", { month: "short" });
}

function shortLabel(name: string, max = 14): string {
  return name.length > max ? `${name.slice(0, max - 1)}…` : name;
}

function KpiCard({
  label,
  icon,
  value,
  accent,
  hidden,
}: {
  label: string;
  icon: ReactNode;
  value: string;
  accent: string;
  hidden: boolean;
}) {
  return (
    <div className="glass-panel clip-rounded-lg flex min-h-28 flex-col justify-between rounded-lg p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-on-surface-variant">{label}</span>
        <div
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
          style={{ background: `${accent}1a`, color: accent }}
        >
          {icon}
        </div>
      </div>
      <div className="text-2xl font-semibold text-on-surface">
        {hidden ? "••••" : value}
      </div>
    </div>
  );
}

function ChartCard({
  title,
  right,
  children,
  empty,
}: {
  title: string;
  right?: ReactNode;
  children: ReactNode;
  empty?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <section className="glass-panel clip-rounded-2xl rounded-2xl p-4 md:p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-on-surface">{title}</h2>
        {right}
      </div>
      {empty ? (
        <p className="flex h-64 items-center justify-center text-center text-sm text-on-surface-variant">
          {t("analytics.empty")}
        </p>
      ) : (
        children
      )}
    </section>
  );
}

function Donut({
  data,
  currency,
  hidden,
}: {
  data: BusinessAnalyticsCategory[];
  currency: string;
  hidden: boolean;
}) {
  const { t } = useTranslation();
  const total = data.reduce((sum, c) => sum + c.value, 0);
  const top = data.slice(0, 5);
  if (data.length === 0) {
    return (
      <p className="flex h-64 items-center justify-center text-center text-sm text-on-surface-variant">
        {t("analytics.empty")}
      </p>
    );
  }
  return (
    <div className="flex flex-col items-center gap-4">
      <div className="relative h-52 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="label"
              innerRadius="58%"
              outerRadius="84%"
              paddingAngle={2}
              stroke="none"
            >
              {data.map((c, i) => (
                <Cell key={c.label} fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]} />
              ))}
            </Pie>
            <Tooltip content={<ChartTooltip currency={currency} />} />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xs text-on-surface-variant">{t("analytics.total")}</span>
          <span className="text-lg font-bold text-on-surface">
            {hidden ? "••••" : formatMoney(total, currency, { symbol: true })}
          </span>
        </div>
      </div>
      <ul className="w-full space-y-2">
        {top.map((c, i) => (
          <li key={c.label} className="flex items-center justify-between gap-3 text-sm">
            <span className="flex min-w-0 items-center gap-2 text-on-surface">
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ background: CATEGORY_COLORS[i % CATEGORY_COLORS.length] }}
              />
              <span className="truncate">{shortLabel(c.label, 22)}</span>
            </span>
            <span className="flex items-center gap-2">
              <span className="text-xs text-on-surface-variant">
                {total > 0 ? `${Math.round((c.value / total) * 100)}%` : ""}
              </span>
              <span className="font-medium text-on-surface">
                {hidden ? "••••" : formatCompact(c.value, currency)}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function AnalyticsPage() {
  const { t } = useTranslation();
  const [months, setMonths] = useState<"6" | "12">("12");
  const [catMode, setCatMode] = useState<"income" | "expense">("income");
  const { data, isLoading, isError, refetch } = useBusinessAnalytics(Number(months));
  const { hidden } = useHideBalances();

  const currency = data?.currency ?? "USD";
  const kpis = data?.kpis;

  const pnlData: BusinessAnalyticsPnlRow[] = useMemo(
    () => data?.pnl ?? Array.from({ length: Number(months) }, () => ({ month: "", income: 0, expense: 0, net: 0 })),
    [data, months]
  );

  const cats = catMode === "income" ? (data?.incomeCategories ?? []) : (data?.expenseCategories ?? []);
  const aging = (data?.aging ?? []).map((row) => ({
    ...row,
    label: t(`analytics.aging.${row.bucket}`),
  }));
  const clients = data?.topClients ?? [];
  const suppliers = data?.topSuppliers ?? [];

  const hasData =
    Boolean(data) &&
    (pnlData.some((r) => r.income !== 0 || r.expense !== 0) ||
      (data?.incomeCategories?.length ?? 0) > 0 ||
      (data?.expenseCategories?.length ?? 0) > 0 ||
      (data?.aging?.reduce((s, r) => s + r.value, 0) ?? 0) > 0 ||
      (data?.topClients?.length ?? 0) > 0 ||
      (data?.topSuppliers?.length ?? 0) > 0);

  const marginValue =
    kpis?.marginPct == null
      ? "—"
      : `${new Intl.NumberFormat("es-VE", { maximumFractionDigits: 1 }).format(kpis.marginPct)}%`;

  const money = (amount?: number) =>
    amount == null ? "—" : formatMoney(amount, currency, { symbol: true });

  if (isError) {
    return (
      <div className="glass-panel clip-rounded-lg mt-6 rounded-lg p-6 text-center">
        <p className="mb-3 text-sm text-on-surface-variant">⚠️ {t("errors.generic")}</p>
        <Button size="sm" variant="outline" onClick={() => refetch()}>
          {t("common.retry")}
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-on-surface md:text-3xl">
            {t("analytics.title")}
          </h1>
          <p className="mt-1 text-sm text-on-surface-variant">{t("analytics.subtitle")}</p>
        </div>
        <Segmented
          layoutId="seg-analytics-months"
          size="sm"
          options={[
            { value: "6", label: t("analytics.months6") },
            { value: "12", label: t("analytics.months12") },
          ]}
          value={months}
          onChange={setMonths}
        />
      </div>

      {isLoading ? (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-4 md:gap-3">
            {Array.from({ length: 7 }).map((_, i) => (
              <Skeleton key={i} className="h-28 w-full" />
            ))}
          </div>
          <Skeleton className="h-80 w-full" />
          <Skeleton className="h-80 w-full" />
        </div>
      ) : (
        <>
          <section className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-4 md:gap-3">
            <KpiCard
              label={t("analytics.kpis.incomePeriod")}
              icon={<TrendingUp className="h-4 w-4" />}
              value={money(kpis?.incomePeriod)}
              accent="var(--color-income)"
              hidden={hidden}
            />
            <KpiCard
              label={t("analytics.kpis.expensePeriod")}
              icon={<TrendingDown className="h-4 w-4" />}
              value={money(kpis?.expensePeriod)}
              accent="var(--color-expense)"
              hidden={hidden}
            />
            <KpiCard
              label={t("analytics.kpis.margin")}
              icon={<Percent className="h-4 w-4" />}
              value={marginValue}
              accent="var(--color-navi)"
              hidden={hidden}
            />
            <KpiCard
              label={t("analytics.kpis.receivable")}
              icon={<HandCoins className="h-4 w-4" />}
              value={money(kpis?.receivable)}
              accent="var(--color-primary)"
              hidden={hidden}
            />
            <KpiCard
              label={t("analytics.kpis.payable")}
              icon={<Wallet className="h-4 w-4" />}
              value={money(kpis?.payable)}
              accent="var(--color-primary-fixed)"
              hidden={hidden}
            />
            <KpiCard
              label={t("analytics.kpis.overdue")}
              icon={<AlertTriangle className="h-4 w-4" />}
              value={money(kpis?.overdue)}
              accent="var(--color-expense)"
              hidden={hidden}
            />
            <KpiCard
              label={t("analytics.kpis.inventory")}
              icon={<Boxes className="h-4 w-4" />}
              value={money(kpis?.inventoryValue)}
              accent="#22d3ee"
              hidden={hidden}
            />
          </section>

          <ChartCard title={t("analytics.pnlTitle")} empty={!hasData}>
            <div className="h-72 w-full min-w-0">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={pnlData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-outline-variant)" vertical={false} />
                  <XAxis
                    dataKey="month"
                    tickFormatter={fmtMonth}
                    tick={{ fill: "var(--color-on-surface-variant)", fontSize: 12 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tickFormatter={(v: number) => formatCompact(v, currency)}
                    tick={{ fill: "var(--color-on-surface-variant)", fontSize: 12 }}
                    axisLine={false}
                    tickLine={false}
                    width={70}
                  />
                  <Tooltip content={<ChartTooltip currency={currency} />} />
                  <Bar
                    dataKey="income"
                    name={t("analytics.pnlIncome")}
                    fill="var(--color-income)"
                    radius={[6, 6, 0, 0]}
                    maxBarSize={26}
                  />
                  <Bar
                    dataKey="expense"
                    name={t("analytics.pnlExpense")}
                    fill="var(--color-expense)"
                    radius={[6, 6, 0, 0]}
                    maxBarSize={26}
                  />
                  <Line
                    type="monotone"
                    dataKey="net"
                    name={t("analytics.pnlNet")}
                    stroke="var(--color-navi)"
                    strokeWidth={2.5}
                    dot={{ r: 3, fill: "var(--color-navi)" }}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </ChartCard>

          <div className="grid gap-4 md:grid-cols-2">
            <ChartCard
              title={t("analytics.categoriesTitle")}
              right={
                <Segmented
                  layoutId="seg-analytics-cat"
                  size="sm"
                  options={[
                    { value: "income", label: t("analytics.categoriesIncome") },
                    { value: "expense", label: t("analytics.categoriesExpense") },
                  ]}
                  value={catMode}
                  onChange={setCatMode}
                />
              }
            >
              <Donut data={cats} currency={currency} hidden={hidden} />
            </ChartCard>

            <ChartCard title={t("analytics.agingTitle")} empty={aging.every((r) => r.value === 0)}>
              <div className="flex h-64 min-w-0 items-center">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={aging} layout="vertical" margin={{ top: 4, right: 24, left: 0, bottom: 4 }}>
                    <XAxis type="number" hide />
                    <YAxis
                      type="category"
                      dataKey="label"
                      width={116}
                      tick={{ fill: "var(--color-on-surface-variant)", fontSize: 12 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip content={<ChartTooltip currency={currency} />} />
                    <Bar dataKey="value" fill="var(--color-navi)" radius={[0, 6, 6, 0]} maxBarSize={20}>
                      <LabelList
                        dataKey="value"
                        position="right"
                        formatter={(item: unknown) =>
                          hidden ? "••••" : formatCompact(Number(item ?? 0), currency)
                        }
                        style={{ fill: "var(--color-on-surface-variant)", fontSize: 12 }}
                      />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <ChartCard title={t("analytics.topClientsTitle")} empty={clients.length === 0}>
              <div className="h-64 min-w-0">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={clients} margin={{ top: 20, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-outline-variant)" vertical={false} />
                    <XAxis
                      dataKey="label"
                      interval={0}
                      tickFormatter={shortLabel}
                      tick={{ fill: "var(--color-on-surface-variant)", fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      tickFormatter={(v: number) => formatCompact(v, currency)}
                      tick={{ fill: "var(--color-on-surface-variant)", fontSize: 12 }}
                      axisLine={false}
                      tickLine={false}
                      width={70}
                    />
                    <Tooltip content={<ChartTooltip currency={currency} />} />
                    <Bar dataKey="value" fill="var(--color-income)" radius={[6, 6, 0, 0]} maxBarSize={36}>
                      <LabelList
                        dataKey="value"
                        position="top"
                        formatter={(item: unknown) =>
                          hidden ? "••••" : formatCompact(Number(item ?? 0), currency)
                        }
                        style={{ fill: "var(--color-on-surface-variant)", fontSize: 11 }}
                      />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>

            <ChartCard title={t("analytics.topSuppliersTitle")} empty={suppliers.length === 0}>
              <div className="h-64 min-w-0">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={suppliers} margin={{ top: 20, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-outline-variant)" vertical={false} />
                    <XAxis
                      dataKey="label"
                      interval={0}
                      tickFormatter={shortLabel}
                      tick={{ fill: "var(--color-on-surface-variant)", fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      tickFormatter={(v: number) => formatCompact(v, currency)}
                      tick={{ fill: "var(--color-on-surface-variant)", fontSize: 12 }}
                      axisLine={false}
                      tickLine={false}
                      width={70}
                    />
                    <Tooltip content={<ChartTooltip currency={currency} />} />
                    <Bar dataKey="value" fill="var(--color-navi)" radius={[6, 6, 0, 0]} maxBarSize={36}>
                      <LabelList
                        dataKey="value"
                        position="top"
                        formatter={(item: unknown) =>
                          hidden ? "••••" : formatCompact(Number(item ?? 0), currency)
                        }
                        style={{ fill: "var(--color-on-surface-variant)", fontSize: 11 }}
                      />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>
          </div>
        </>
      )}
    </div>
  );
}