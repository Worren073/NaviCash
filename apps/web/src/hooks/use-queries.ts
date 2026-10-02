import { useQuery } from "@tanstack/react-query";

import { api, ApiErrorClass } from "@/lib/api";
import type {
  Business,
  BusinessContact,
  BusinessSummary,
  Checklist,
  NotificationsResponse,
  Overview,
  Paginated,
  Subscription,
  User,
  Wallet,
} from "@/lib/types";

export const queryKeys = {
  overview: ["overview"] as const,
  wallets: ["wallets"] as const,
  categories: ["categories"] as const,
  contacts: ["contacts"] as const,
  transactions: ["transactions"] as const,
  savings: ["savings"] as const,
  me: ["me"] as const,
  rates: ["rates"] as const,
  ratesEuro: ["rates-euro"] as const,
  notifications: ["notifications"] as const,
  subscriptions: ["subscriptions"] as const,
  checklists: ["checklists"] as const,
  business: ["business"] as const,
  businessSummary: ["business-summary"] as const,
  businessContacts: ["business-contacts"] as const,
};

export function useOverview() {
  return useQuery({
    queryKey: queryKeys.overview,
    queryFn: ({ signal }) => api.get<Overview>("/overview", { signal }),
  });
}

export function useMe() {
  return useQuery({
    queryKey: queryKeys.me,
    queryFn: ({ signal }) => api.get<User>("/auth/me", { signal }),
  });
}

export function useWallets() {
  return useQuery({
    queryKey: queryKeys.wallets,
    queryFn: ({ signal }) =>
      api.get<{ results: Wallet[] }>("/wallets", { signal }).then((d) => d.results),
  });
}

export function useNotifications(scope: "personal" | "business" = "personal") {
  return useQuery({
    queryKey: [...queryKeys.notifications, scope],
    queryFn: ({ signal }) =>
      api.get<NotificationsResponse>(`/notifications?scope=${scope}`, { signal }),
  });
}

export function useSubscriptions() {
  return useQuery({
    queryKey: queryKeys.subscriptions,
    queryFn: ({ signal }) =>
      api.get<{ results: Subscription[] }>("/subscriptions", { signal }).then((d) => d.results),
  });
}

export function useChecklists() {
  return useQuery({
    queryKey: queryKeys.checklists,
    queryFn: ({ signal }) =>
      api.get<{ results: Checklist[] }>("/checklists", { signal }).then((d) => d.results),
  });
}

/** Perfil del negocio del usuario; ``null`` si aún no lo ha creado (404). */
export function useBusiness() {
  return useQuery({
    queryKey: queryKeys.business,
    queryFn: async ({ signal }) => {
      try {
        return await api.get<Business>("/business", { signal });
      } catch (err) {
        if (err instanceof ApiErrorClass && err.status === 404) return null;
        throw err;
      }
    },
  });
}

export function useBusinessSummary() {
  return useQuery({
    queryKey: queryKeys.businessSummary,
    queryFn: ({ signal }) => api.get<BusinessSummary>("/business/summary", { signal }),
  });
}

export function useBusinessContacts(search?: string, type?: string) {
  return useQuery({
    queryKey: [...queryKeys.businessContacts, { search, type }],
    queryFn: ({ signal }) => {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      if (type) params.set("type", type);
      return api.get<Paginated<BusinessContact>>(`/business/contacts?${params.toString()}`, {
        signal,
      });
    },
  });
}