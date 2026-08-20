// Tipos del contrato REST de NaviCash (coinciden con los serializers Django).

export type Currency = "USD" | "VES";
export type TxType = "cobro" | "pago" | "transferencia";
export type TxState = "pendiente" | "pagado" | "retrasado" | "cancelado";

export interface User {
  id: string;
  email: string;
  name: string;
  first_name: string;
  last_name: string;
  phone: string;
  base_currency: Currency;
  timezone_name: string;
  reminder_days: number;
  is_onboarded: boolean;
}

export interface Wallet {
  id: string;
  name: string;
  currency: Currency;
  saldo: string;
  tipo: "cash" | "bank" | "saving" | "other";
  color: string;
  created_at: string;
}

export interface Category {
  id: string;
  name: string;
  icon: string;
  tipo: "ingreso" | "egreso" | "transferencia";
  is_default: boolean;
}

export interface Contact {
  id: string;
  name: string;
  note: string;
}

export interface Transaction {
  id: string;
  tipo: TxType;
  estado: TxState;
  effective_state: TxState | null;
  is_overdue: boolean;
  monto: string;
  moneda: Currency;
  monto_usd: string;
  tasa_usd: string;
  fuente_tasa: string;
  concepto: string;
  contact: string | null;
  category: string | null;
  wallet: string | null;
  wallet_name: string | null;
  dest_wallet: string | null;
  dest_wallet_name: string | null;
  monto_destino: string;
  moneda_destino: Currency;
  tasa_uso: string;
  tasa_fuente: "oficial" | "manual";
  fecha: string;
  fecha_vencimiento: string | null;
  fecha_pagado: string | null;
  remind_me: boolean;
  reminder_days: number | null;
  nota: string;
  created_at: string;
}

export interface LinkedAccount {
  id: string;
  name: string;
  currency: Currency;
  saldo: string;
}

export interface SavingsGoal {
  id: string;
  name: string;
  target_amount: string;
  currency: Currency;
  target_date: string | null;
  total_contributed: string;
  progress_percent: string;
  contributions_count: number;
  linked_accounts: Array<LinkedAccount>;
  created_at: string;
}

export interface Shortcut {
  id: string;
  label: string;
  kind: "transaction" | "goal_contribution";
  config: Record<string, unknown>;
  order: number;
  icon: string | null;
}

export interface Overview {
  base_currency: Currency;
  rate: string | null;
  total_balance_usd: string;
  total_balance_ves: string | null;
  to_receive: string;
  to_pay: string;
  count_to_receive: number;
  count_to_pay: number;
  overdue: string;
  wallets: Array<WalletSummary>;
  upcoming: Transaction[];
  recent: Transaction[];
}

export interface WalletSummary {
  id: string;
  name: string;
  currency: Currency;
  saldo: string;
  usd_value: string;
}

export interface CategoryRow {
  category: string;
  total: string;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface NotificationItem {
  id: string;
  kind: "due_soon" | "overdue" | "goal_reached" | "system";
  title: string;
  message: string;
  extra: Record<string, unknown>;
  read: boolean;
  created_at: string;
}

export interface NotificationsResponse {
  results: NotificationItem[];
  unread_count: number;
}

export type SubscriptionStatus = "proxima" | "activa" | "finalizada";

export interface Subscription {
  id: string;
  name: string;
  color: string;
  start_date: string;
  end_date: string;
  progress_percent: string;
  days_total: number;
  days_elapsed: number;
  days_remaining: number;
  status: SubscriptionStatus;
  can_renew: boolean;
  created_at: string;
}