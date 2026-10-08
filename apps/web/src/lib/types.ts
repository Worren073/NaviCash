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
  /** Fecha de purga definitiva; null = cuenta normal (gracia no iniciada). */
  deletion_scheduled_at: string | null;
}

export interface Wallet {
  id: string;
  name: string;
  currency: Currency;
  saldo: string;
  tipo: "cash" | "bank" | "saving" | "other" | "business";
  color: string;
  created_at: string;
}

export interface Business {
  id: string;
  name: string;
  currency: Currency;
  wallet_id: string;
  saldo: string;
  created_at: string;
}

export interface BusinessSummary {
  saldo: string;
  currency: Currency;
  ingresos_mes: string;
  egresos_mes: string;
  recent: Transaction[];
}

export interface BusinessAnalyticsPnlRow {
  month: string;
  income: number;
  expense: number;
  net: number;
}

export interface BusinessAnalyticsCategory {
  label: string;
  value: number;
}

export interface BusinessAnalyticsAging {
  bucket: "0_30" | "31_60" | "61_90" | "90";
  value: number;
}

export interface BusinessAnalyticsTop {
  label: string;
  value: number;
}

export interface BusinessAnalyticsKpis {
  incomePeriod: number;
  expensePeriod: number;
  marginPct: number | null;
  receivable: number;
  payable: number;
  overdue: number;
  inventoryValue: number;
}

export interface BusinessAnalytics {
  currency: Currency;
  months: number;
  pnl: BusinessAnalyticsPnlRow[];
  incomeCategories: BusinessAnalyticsCategory[];
  expenseCategories: BusinessAnalyticsCategory[];
  aging: BusinessAnalyticsAging[];
  topClients: BusinessAnalyticsTop[];
  topSuppliers: BusinessAnalyticsTop[];
  kpis: BusinessAnalyticsKpis;
}

export interface BusinessContact {
  id: string;
  business: string;
  name: string;
  email: string;
  phone: string;
  address: string;
  tax_id: string;
  type: "cliente" | "proveedor" | "ambos";
  customer_type: "minorista" | "mayorista" | "";
  payment_terms_days: number;
  credit_limit: string | null;
  currency: Currency;
  notes: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export type InvoiceStatus =
  | "borrador"
  | "enviada"
  | "parcial"
  | "pagada"
  | "vencida"
  | "anulada";

export interface InvoiceItem {
  id: string;
  product: string | null;
  description: string;
  quantity: string;
  unit_price: string;
  discount: string;
  total: string;
}

export interface InvoicePayment {
  id: string;
  transaction_id: string | null;
  amount: string;
  paid_at: string;
  note: string;
}

export interface Invoice {
  id: string;
  business: string;
  contact: BusinessContact;
  number: string;
  issue_date: string;
  due_date: string;
  status: InvoiceStatus;
  subtotal: string;
  tax_amount: string;
  total: string;
  amount_paid: string;
  balance_due: string;
  currency: Currency;
  notes: string;
  items: InvoiceItem[];
  payments: InvoicePayment[];
  latest_follow_up: LatestFollowUp | null;
  created_at: string;
  updated_at: string;
}

export interface InvoiceDraft {
  contact: string;
  items: { product?: string; description: string; quantity: string; unit_price: string; discount?: string }[];
  issue_date?: string;
  due_date?: string;
  tax_amount?: string;
  paid_amount?: string;
  notes?: string;
}

export interface ProductCategory {
  id: string;
  name: string;
  business: string;
}

export interface Product {
  id: string;
  name: string;
  sku: string | null;
  description: string;
  unit: string | null;
  unit_price: string;
  wholesale_price: string | null;
  cost_price: string;
  category: string | null;
  supplier: string | null;
  stock_quantity: string;
  low_stock_threshold: string;
  is_active: boolean;
  is_low_stock: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProductDraft {
  name: string;
  sku?: string;
  description?: string;
  unit?: string;
  unit_price?: string;
  wholesale_price?: string;
  cost_price?: string;
  category?: string;
  supplier?: string;
  low_stock_threshold?: string;
  is_active?: boolean;
}

export type OrderStatus = "borrador" | "en_camino" | "recibido" | "anulado";

export type OrderPaymentState = "none" | "partial" | "paid";

/** Producto nuevo ingresado inline en un pedido; se crea al recibir el pedido. */
export interface OrderNewProduct {
  name: string;
  sku: string;
  unit: "unidad" | "kg";
  category: string | null;
  unit_price: string;
  wholesale_price: string | null;
  cost_price: string | null;
  low_stock_threshold: string | null;
  is_active: boolean;
}

export interface OrderItem {
  id: string;
  product: string | null;
  new_product: OrderNewProduct | null;
  description: string;
  quantity: string;
  unit_price: string;
  discount: string;
  total: string;
}

export interface OrderPayment {
  id: string;
  transaction_id: string | null;
  amount: string;
  paid_at: string;
  note: string;
}

export interface Order {
  id: string;
  business: string;
  contact: BusinessContact;
  number: string;
  order_date: string;
  due_date: string | null;
  received_at: string | null;
  status: OrderStatus;
  payment_state: OrderPaymentState;
  subtotal: string;
  shipping_amount: string;
  total: string;
  amount_paid: string;
  balance_due: string;
  currency: Currency;
  notes: string;
  items: OrderItem[];
  payments: OrderPayment[];
  created_at: string;
  updated_at: string;
}

/** Linea editable de un pedido: producto del inventario o producto nuevo. */
export interface OrderLineDraft {
  product?: string;
  new_product?: OrderNewProduct;
  description: string;
  quantity: string;
  unit_price?: string;
  discount?: string;
}

/** Prefill del CTA «aprovisionar desde stock bajo» (state del router). */
export interface OrderPrefillLine {
  product: string;
  quantity: string;
  unit_price: string;
}

export type CollectionChannel = "llamada" | "email" | "whatsapp" | "visita" | "otro";

export type CollectionOutcome =
  | "sin_respuesta"
  | "promesa_pago"
  | "pago_realizado"
  | "rechazado"
  | "otro";

interface LatestFollowUp {
  id: string;
  channel: CollectionChannel;
  outcome: CollectionOutcome;
  promised_date: string | null;
  notes: string;
  created_at: string;
}

export interface CollectionFollowUp {
  id: string;
  invoice: string;
  channel: CollectionChannel;
  outcome: CollectionOutcome;
  promised_date: string | null;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface CollectionFollowUpDraft {
  invoice: string;
  channel: CollectionChannel;
  outcome: CollectionOutcome;
  promised_date?: string;
  notes?: string;
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
  euro_rate: string | null;
  total_balance_usd: string;
  total_balance_ves: string | null;
  to_receive: string;
  to_pay: string;
  count_to_receive: number;
  count_to_pay: number;
  overdue: string;
  collected_month: string;
  spent_month: string;
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
  scope: "personal" | "business";
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
  amount: string | null;
  currency: string;
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

export type ChecklistState = "en_curso" | "completada";

export interface ChecklistItem {
  id: string;
  name: string;
  precio_unitario: string | null;
  cantidad: number;
  is_checked: boolean;
  subtotal: string;
  created_at: string;
}

export interface Checklist {
  id: string;
  name: string;
  currency: Currency;
  estado: ChecklistState;
  total_estimado: string;
  progress_percent: string;
  total_real: string | null;
  wallet: string | null;
  wallet_name: string | null;
  transaction: string | null;
  completed_at: string | null;
  items: ChecklistItem[];
  created_at: string;
}