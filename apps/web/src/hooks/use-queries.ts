import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { NotificationsResponse, Overview, Subscription, Wallet } from "@/lib/types";

export const queryKeys = {
  overview: ["overview"] as const,
  wallets: ["wallets"] as const,
  categories: ["categories"] as const,
  contacts: ["contacts"] as const,
  transactions: ["transactions"] as const,
  savings: ["savings"] as const,
  shortcuts: ["shortcuts"] as const,
  me: ["me"] as const,
  rates: ["rates"] as const,
  notifications: ["notifications"] as const,
  subscriptions: ["subscriptions"] as const,
};

export function useOverview() {
  return useQuery({
    queryKey: queryKeys.overview,
    queryFn: () => api.get<Overview>("/overview"),
  });
}

export function useWallets() {
  return useQuery({
    queryKey: queryKeys.wallets,
    queryFn: () => api.get<{ results: Wallet[] }>("/wallets").then((d) => d.results),
  });
}

export function useNotifications() {
  return useQuery({
    queryKey: queryKeys.notifications,
    queryFn: () => api.get<NotificationsResponse>("/notifications"),
  });
}

export function useSubscriptions() {
  return useQuery({
    queryKey: queryKeys.subscriptions,
    queryFn: () => api.get<{ results: Subscription[] }>("/subscriptions").then((d) => d.results),
  });
}