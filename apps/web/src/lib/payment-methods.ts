// Métodos de pago del CRM y su moneda. Espejo de apps/crm/payment_methods.py.

import type { Currency, PaymentMethod } from "./types";

export interface PaymentMethodOption {
  value: PaymentMethod;
  currency: Currency;
  /** Clave i18n del nombre visible. */
  labelKey: string;
}

export const PAYMENT_METHODS: PaymentMethodOption[] = [
  { value: "pago_movil", currency: "VES", labelKey: "paymentMethods.pago_movil" },
  { value: "transferencia", currency: "VES", labelKey: "paymentMethods.transferencia" },
  { value: "efectivo_ves", currency: "VES", labelKey: "paymentMethods.efectivo_ves" },
  { value: "efectivo_usd", currency: "USD", labelKey: "paymentMethods.efectivo_usd" },
  { value: "binance", currency: "USD", labelKey: "paymentMethods.binance" },
  { value: "zelle", currency: "USD", labelKey: "paymentMethods.zelle" },
];

const CURRENCY_BY_METHOD: Record<PaymentMethod, Currency> = PAYMENT_METHODS.reduce(
  (acc, m) => ({ ...acc, [m.value]: m.currency }),
  {} as Record<PaymentMethod, Currency>,
);

/** Moneda del documento (VES o USD) que define un método de pago. */
export function methodCurrency(method: PaymentMethod): Currency {
  return CURRENCY_BY_METHOD[method] ?? "USD";
}

/** Método por defecto para una moneda (VES → Pago Móvil, USD → Zelle). */
export function defaultMethodFor(currency: Currency): PaymentMethod {
  return currency === "VES" ? "pago_movil" : "zelle";
}
