// Tipos del contrato REST de NaviCash (coinciden con los serializers Django).

export type Currency = "USD" | "VES";
export type TxType = "cobro" | "pago" | "transferencia";
export type TxState = "pendiente" | "pagado" | "retrasado" | "cancelado";

export type WalletRole = "primary" | "secondary";

/** Métodos de pago del CRM; su moneda define la cuenta y la moneda del documento. */
export type PaymentMethod =
  | "pago_movil"
  | "transferencia"
  | "efectivo_ves"
  | "efectivo_usd"
  | "binance"
  | "zelle";

/** Cuenta de un negocio (una en VES y otra en USD). */
export interface BusinessAccount {
  id: string;
  name: string;
  currency: Currency;
  role: WalletRole;
  balance: string;
}

/** Equivalencia de un documento en su otra moneda (pagado congelado, saldo vivo). */
export interface CurrencyConversion {
  currency: Currency;
  rate: string | null;
  total: string | null;
  paid: string | null;
  balance: string | null;
  frozen: boolean;
}

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
  role: WalletRole;
  color: string;
  created_at: string;
}

export interface Business {
  id: string;
  name: string;
  currency: Currency;
  wallet_id: string;
  saldo: string;
  accounts: BusinessAccount[];
  created_at: string;
}

export interface BusinessSummary {
  saldo: string;
  currency: Currency;
  accounts: BusinessAccount[];
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

export interface BusinessAnalyticsDailyRow {
  date: string;
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

export interface BusinessAnalyticsTopProduct {
  label: string;
  quantity: number;
  revenue: number;
  margin: number;
}

export interface BusinessAnalyticsKpis {
  incomePeriod: number;
  expensePeriod: number;
  marginPct: number | null;
  receivable: number;
  payable: number;
  overdue: number;
  inventoryValue: number;
  /** Unidades de servicios facturadas en el periodo. */
  serviceUnits: number;
  /** Monto facturado por servicios (USD) en el periodo. */
  serviceRevenue: number;
}

export interface BusinessAnalytics {
  currency: Currency;
  months: number;
  /** Mes elegido (YYYY-MM) o null cuando se ve la ventana completa. */
  month: string | null;
  pnl: BusinessAnalyticsPnlRow[];
  /** Desglose por día del mes elegido (vacío si no hay mes). */
  daily: BusinessAnalyticsDailyRow[];
  incomeCategories: BusinessAnalyticsCategory[];
  expenseCategories: BusinessAnalyticsCategory[];
  aging: BusinessAnalyticsAging[];
  topClients: BusinessAnalyticsTop[];
  topSuppliers: BusinessAnalyticsTop[];
  /** Top 5 de productos físicos por unidades vendidas en el periodo. */
  topProducts: BusinessAnalyticsTopProduct[];
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
  payment_method: PaymentMethod;
  paid_currency: Currency;
  paid_amount: string;
  rate_usd: string;
  paid_at: string;
  note: string;
}

export interface Invoice {
  id: string;
  business: string;
  contact: BusinessContact;
  number: string;
  issue_date: string;
  issued_at: string | null;
  due_date: string;
  status: InvoiceStatus;
  subtotal: string;
  tax_amount: string;
  total: string;
  amount_paid: string;
  balance_due: string;
  currency: Currency;
  conversion: CurrencyConversion | null;
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
  issued_at?: string;
  due_date?: string;
  tax_amount?: string;
  paid_amount?: string;
  payment_method?: PaymentMethod;
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
  kind: "producto" | "servicio";
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
  payment_method: PaymentMethod;
  paid_currency: Currency;
  paid_amount: string;
  rate_usd: string;
  paid_at: string;
  note: string;
}

export interface Order {
  id: string;
  business: string;
  contact: BusinessContact;
  number: string;
  order_date: string;
  ordered_at: string | null;
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
  conversion: CurrencyConversion | null;
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

// ---------------------------------------------------------------------------
// Mensajería de redes sociales (WhatsApp Cloud API / Instagram Login)
// ---------------------------------------------------------------------------

export type ChatPlatform = "whatsapp" | "instagram";
export type ChatConversationStatus = "abierta" | "archivada";

/** Hilo de conversación con un cliente en una red social. */
export interface ChatConversation {
  id: string;
  platform: ChatPlatform;
  /** Identificador del interlocutor en la plataforma (wa_id/teléfono o IGSID). */
  external_id: string;
  contact: string | null;
  contact_name: string;
  avatar_url: string;
  last_message_at: string | null;
  last_message_preview: string;
  unread_count: number;
  status: ChatConversationStatus;
  created_at: string;
}

export type ChatMessageDirection = "in" | "out";
export type ChatMessageStatus = "received" | "sent" | "delivered" | "read" | "failed";

/** Adjunto de un mensaje (imagen, video, audio o archivo). */
export interface ChatAttachment {
  id: string;
  kind: string;
  /** URL servible (archivo rehospedado en el object storage o remoto). */
  url: string;
  remote_url: string;
  mime: string;
  size: number | null;
  filename: string;
}

/** Mensaje individual dentro de una conversación. */
export interface ChatMessage {
  id: string;
  direction: ChatMessageDirection;
  message_type: string;
  body: string;
  status: ChatMessageStatus;
  attachments: ChatAttachment[];
  created_at: string;
}

/**
 * Credenciales de WhatsApp del negocio. Los secretos nunca llegan al cliente:
 * solo se informa si están presentes (``has_access_token`` / ``has_app_secret``).
 */
export interface WhatsAppConfig {
  connected: boolean;
  phone_number_id?: string;
  waba_id?: string;
  display_phone_number?: string;
  is_active?: boolean;
  /** Secreto de handshake del webhook; el dueño lo pega en el panel de Meta. */
  verify_token?: string;
  has_access_token?: boolean;
  has_app_secret?: boolean;
  updated_at?: string;
}

/** Datos editables de la conexión de WhatsApp (alta o actualización). */
export interface WhatsAppConfigDraft {
  phone_number_id: string;
  display_phone_number?: string;
  waba_id?: string;
  access_token?: string;
  app_secret?: string;
}

/**
 * Estado de la conexión de Instagram del negocio. El token nunca llega al
 * cliente: solo se informa si está presente (``has_access_token``).
 */
export interface InstagramConfig {
  connected: boolean;
  ig_user_id?: string;
  username?: string;
  is_active?: boolean;
  has_access_token?: boolean;
  token_expires_at?: string | null;
  updated_at?: string;
}

/** Respuesta del endpoint de inicio del OAuth de Instagram. */
export interface InstagramOAuthStart {
  authorize_url: string;
}