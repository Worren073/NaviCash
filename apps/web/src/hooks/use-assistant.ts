import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { useQuery } from "@tanstack/react-query";
import { useOverview, useSubscriptions, useWallets, queryKeys } from "@/hooks/use-queries";
import { useNavView } from "@/features/navigation/nav-view";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { BusinessAnalytics, BusinessSummary, SavingsGoal } from "@/lib/types";

export interface AssistantMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
}

export interface AssistantReply {
  text: string;
  session_id: string;
  view?: "personal" | "business";
}

let nextId = 0;
const uid = () => `m${++nextId}`;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * Hook del asistente "Navi".
 *
 * Fase 1 (per `docs/AI-ASSISTANT.md`): envía el mensaje al backend
 * (`POST /api/assistant/messages`), que responde anclado al contexto real del
 * usuario (con proveedor LLM configurado o fallback determinista). Si la
 * llamada falla (sin red, rate limit, 5xx) se responde con la lógica
 * determinista local — el asistente nunca deja de responder.
 */
export function useAssistant() {
  const { t } = useTranslation();
  const { view } = useNavView();
  const overview = useOverview();
  const wallets = useWallets();
  const subscriptions = useSubscriptions();
  const { data: goals } = useQuery({
    queryKey: queryKeys.savings,
    queryFn: ({ signal }) =>
      api.get<{ results: SavingsGoal[] }>("/savings", { signal }).then((d) => d.results),
  });

  // Datos del negocio solo cuando la vista es negocios (evita pedirlos en la
  // vista personal o a usuarios sin negocio). Alimentan el fallback local.
  const { data: businessSummary } = useQuery({
    queryKey: queryKeys.businessSummary,
    queryFn: ({ signal }) => api.get<BusinessSummary>("/business/summary", { signal }),
    enabled: view === "business",
    retry: false,
  });
  const { data: businessAnalytics } = useQuery({
    queryKey: [...queryKeys.businessAnalytics, 6],
    queryFn: ({ signal }) =>
      api.get<BusinessAnalytics>("/business/analytics?months=6", { signal }),
    enabled: view === "business",
    retry: false,
  });

  const sessionIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const greeting = t(view === "business" ? "assistant.greetingBusiness" : "assistant.greeting");
  const [messages, setMessages] = useState<AssistantMessage[]>([
    { id: uid(), role: "assistant", text: greeting },
  ]);
  const [thinking, setThinking] = useState(false);

  const answer = useCallback(
    (question: string): string => {
      const q = question.toLowerCase();
      const o = overview.data;
      const ws = wallets.data ?? [];

      // Saldo total y por cuentas.
      if (/saldo|balance|cu[aá]nto tengo|dinero/.test(q)) {
        if (!o) return t("assistant.noData");
        const lines = ws
          .map((w) => `• ${w.name} (${w.currency}): ${formatMoney(w.saldo, w.currency, { symbol: true })}`)
          .join("\n");
        return `${t("assistant.balanceReply", { total: formatMoney(o.total_balance_usd, "USD", { symbol: true }) })}\n${lines}`;
      }

      // Por cobrar.
      if (/cobrar|recibir|ingres[oó]/.test(q)) {
        if (!o) return t("assistant.noData");
        const count = (o.upcoming ?? []).filter((tx) => tx.tipo === "cobro").length;
        return t("assistant.toReceiveReply", {
          amount: formatMoney(o.to_receive, o.base_currency, { symbol: true }),
          count,
        });
      }

      // Por pagar.
      if (/pagar|gasto|debo/.test(q)) {
        if (!o) return t("assistant.noData");
        const count = (o.upcoming ?? []).filter((tx) => tx.tipo === "pago").length;
        return t("assistant.toPayReply", {
          amount: formatMoney(o.to_pay, o.base_currency, { symbol: true }),
          count,
        });
      }

      // Vencidos / retrasados.
      if (/vencid|retrasad|atrasad|vencimient/.test(q)) {
        if (!o) return t("assistant.noData");
        return t("assistant.overdueReply", {
          amount: formatMoney(o.overdue, o.base_currency, { symbol: true }),
        });
      }

      // Ahorro / metas.
      if (/ahor[oó]|meta|ahorrado/.test(q)) {
        const savingsUsd = ws
          .filter((w) => w.tipo === "saving")
          .reduce((acc, w) => acc + Number(w.saldo), 0);
        const lines = (goals ?? [])
          .map((g) => `• ${g.name}: ${g.progress_percent}%`)
          .join("\n");
        return `${t("assistant.savingsReply", { total: formatMoney(savingsUsd, "USD", { symbol: true }) })}\n${lines || t("assistant.noGoals")}`;
      }

      // Mensualidades.
      if (/mensualidad|suscripci[oó]n|subscription/.test(q)) {
        const subs = subscriptions.data ?? [];
        if (subs.length === 0) return t("assistant.noSubscriptions");
        return subs
          .map((s) => `• ${s.name}: ${s.status === "finalizada" ? t("assistant.finished") : `${s.days_remaining} ${t("assistant.daysLeft")}`}`)
          .join("\n");
      }

      // ¿Me puedo permitir X? — aproximación simple ingreso vs gasto.
      if (/permitir|cuesta|alcanza/.test(q)) {
        if (!o) return t("assistant.noData");
        const income = Number(o.to_receive ?? 0);
        const expenses = Number(o.to_pay ?? 0);
        const net = Number(o.total_balance_usd ?? 0) + income - expenses;
        return t("assistant.affordReply", {
          balance: formatMoney(o.total_balance_usd, "USD", { symbol: true }),
          net: formatMoney(net, "USD", { symbol: true }),
        });
      }

      return t("assistant.fallback");
    },
    [t, overview.data, wallets.data, subscriptions.data, goals],
  );

  // Fallback local para la vista de negocio (si el backend no responde).
  const businessAnswer = useCallback(
    (question: string): string => {
      const q = question.toLowerCase();
      if (!businessSummary) return t("assistant.noBusiness");
      const currency = businessSummary.currency;
      if (/saldo|balance|cu[aá]nto tengo|caja|dinero/.test(q)) {
        return t("assistant.businessBalanceReply", {
          total: formatMoney(businessSummary.saldo, currency, { symbol: true }),
        });
      }
      const k = businessAnalytics?.kpis;
      if (/cobrar|me deben|recibir|cartera|factura/.test(q)) {
        if (!k) return t("assistant.businessFallback");
        return t("assistant.businessReceivablesReply", {
          amount: formatMoney(String(k.receivable), currency, { symbol: true }),
          overdue: formatMoney(String(k.overdue), currency, { symbol: true }),
        });
      }
      if (/pagar|debo|proveedor|pedido/.test(q)) {
        if (!k) return t("assistant.businessFallback");
        return t("assistant.businessPayablesReply", {
          amount: formatMoney(String(k.payable), currency, { symbol: true }),
        });
      }
      return t("assistant.businessFallback");
    },
    [t, businessSummary, businessAnalytics],
  );

  const fallbackAnswer = useCallback(
    (question: string): string =>
      view === "business" ? businessAnswer(question) : answer(question),
    [view, businessAnswer, answer],
  );

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || thinking) return;
      abortRef.current = new AbortController();
      setMessages((prev) => [...prev, { id: uid(), role: "user", text: trimmed }]);
      setThinking(true);

      try {
        const reply = await api.post<AssistantReply>(
          "/assistant/messages",
          {
            message: trimmed,
            view,
            ...(sessionIdRef.current ? { session_id: sessionIdRef.current } : {}),
          },
          { signal: abortRef.current.signal }
        );
        sessionIdRef.current = reply.session_id;
        setMessages((prev) => [...prev, { id: uid(), role: "assistant", text: reply.text }]);
      } catch (err) {
        // Abortado (cierre del chat/voz) o timeout: no responder.
        if (abortRef.current?.signal.aborted) return;
        if (err instanceof DOMException && err.name === "AbortError") return;
        // Fallback local: sin red, rate limit o error del servidor.
        await sleep(600);
        if (abortRef.current?.signal.aborted) return;
        setMessages((prev) => [...prev, { id: uid(), role: "assistant", text: fallbackAnswer(trimmed) }]);
      } finally {
        abortRef.current = null;
        setThinking(false);
      }
    },
    [fallbackAnswer, thinking, view],
  );

  // A12 — abortar cualquier petición en curso al desmontar el hook.
  useEffect(() => () => abortRef.current?.abort(), []);

  /** Aborta la petición en curso (p. ej. al cerrar el overlay de voz). */
  const abort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const reset = useCallback(() => {
    sessionIdRef.current = null;
    abort();
    setMessages([{ id: uid(), role: "assistant", text: greeting }]);
  }, [abort, greeting]);

  return { messages, thinking, send, reset, abort };
}
