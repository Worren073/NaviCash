// Tipos del contrato REST de NaviCash (coinciden con los serializers Django).

export type Currency = "USD" | "VES";
export type TxType = "cobro" | "pago";
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
  fecha: string;
  fecha_vencimiento: string | null;
  fecha_pagado: string | null;
  remind_me: boolean;
  reminder_days: number | null;
  nota: string;
  created_at: string;
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
  status: SubscriptionStatus;
  created_at: string;
}