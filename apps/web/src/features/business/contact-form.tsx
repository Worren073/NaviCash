import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { NumericInput } from "@/components/ui/numeric-input";
import type { TaxIdType } from "@/lib/tax-id";
import type { BusinessContact, Currency } from "@/lib/types";
import { TaxIdField } from "./tax-id-field";

const TYPE_OPTIONS = [
  { value: "", label: "contacts.types.all" },
  { value: "cliente", label: "contacts.types.cliente" },
  { value: "proveedor", label: "contacts.types.proveedor" },
  { value: "ambos", label: "contacts.types.ambos" },
];

const CUSTOMER_TYPES = [
  { value: "", label: "contacts.customerTypes.none" },
  { value: "minorista", label: "contacts.customerTypes.minorista" },
  { value: "mayorista", label: "contacts.customerTypes.mayorista" },
];

const CURRENCIES: Currency[] = ["USD", "VES"];

export interface ContactFormValue {
  name: string;
  email: string;
  phone: string;
  address: string;
  tax_id: string;
  type: BusinessContact["type"];
  customer_type: BusinessContact["customer_type"];
  payment_terms_days: number;
  credit_limit: string;
  currency: Currency;
  notes: string;
  is_active: boolean;
}

export function emptyContactForm(): ContactFormValue {
  return {
    name: "",
    email: "",
    phone: "",
    address: "",
    tax_id: "",
    type: "cliente",
    customer_type: "",
    payment_terms_days: 0,
    credit_limit: "",
    currency: "USD",
    notes: "",
    is_active: true,
  };
}

export function ContactForm({
  value,
  onChange,
  fixedTaxIdType,
}: {
  value: ContactFormValue;
  onChange: (next: ContactFormValue) => void;
  /** El tipo de cédula (V/J/E) viene forzado desde el flujo de la factura. */
  fixedTaxIdType?: TaxIdType;
}) {
  const { t } = useTranslation();
  const update = <K extends keyof ContactFormValue>(
    key: K,
    val: ContactFormValue[K],
  ) => onChange({ ...value, [key]: val });

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <label className="block sm:col-span-2">
        <span className="mb-1 block text-sm font-medium text-on-surface">
          {t("contacts.name")}
        </span>
        <Input
          value={value.name}
          onChange={(e) => update("name", e.target.value)}
          placeholder={t("contacts.namePlaceholder")}
        />
      </label>

      <label className="block">
        <span className="mb-1 block text-sm font-medium text-on-surface">
          {t("contacts.type")}
        </span>
        <select
          value={value.type}
          onChange={(e) =>
            update("type", e.target.value as BusinessContact["type"])
          }
          className="h-11 w-full rounded-xl border border-glass-border bg-glass-surface px-3 text-base text-on-surface shadow-sm outline-none backdrop-blur-md focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 md:text-sm"
        >
          {TYPE_OPTIONS.slice(1).map((opt) => (
            <option key={opt.value} value={opt.value}>
              {t(opt.label)}
            </option>
          ))}
        </select>
      </label>

      {value.type !== "proveedor" && (
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-on-surface">
            {t("contacts.customerType")}
          </span>
          <select
            value={value.customer_type}
            onChange={(e) =>
              update(
                "customer_type",
                e.target.value as BusinessContact["customer_type"],
              )
            }
            className="h-11 w-full rounded-xl border border-glass-border bg-glass-surface px-3 text-base text-on-surface shadow-sm outline-none backdrop-blur-md focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 md:text-sm"
          >
            {CUSTOMER_TYPES.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {t(opt.label)}
              </option>
            ))}
          </select>
        </label>
      )}

      <label className="block">
        <span className="mb-1 block text-sm font-medium text-on-surface">
          {t("contacts.email")}
        </span>
        <Input
          type="email"
          value={value.email}
          onChange={(e) => update("email", e.target.value)}
          placeholder={t("contacts.emailPlaceholder")}
        />
      </label>

      <label className="block">
        <span className="mb-1 block text-sm font-medium text-on-surface">
          {t("contacts.phone")}
        </span>
        <Input
          value={value.phone}
          onChange={(e) => update("phone", e.target.value)}
          placeholder={t("contacts.phonePlaceholder")}
        />
      </label>

      <label className="block sm:col-span-2">
        <span className="mb-1 block text-sm font-medium text-on-surface">
          {t("contacts.address")}
        </span>
        <Input
          value={value.address}
          onChange={(e) => update("address", e.target.value)}
          placeholder={t("contacts.addressPlaceholder")}
        />
      </label>

      <div>
        <TaxIdField
          id="contact-tax-id"
          value={value.tax_id}
          onChange={(next) => update("tax_id", next)}
          fixedType={fixedTaxIdType}
        />
      </div>

      <label className="block">
        <span className="mb-1 block text-sm font-medium text-on-surface">
          {t("contacts.paymentTerms")}
        </span>
        <NumericInput
          mode="integer"
          value={String(value.payment_terms_days)}
          onChange={(next) => update("payment_terms_days", Number(next))}
        />
      </label>

      <label className="block sm:col-span-2">
        <span className="mb-1 block text-sm font-medium text-on-surface">
          {t("contacts.creditLimit")}
        </span>
        <div className="flex items-center gap-2">
          <select
            value={value.currency}
            onChange={(e) => update("currency", e.target.value as Currency)}
            className="h-11 rounded-xl border border-glass-border bg-glass-surface px-2 text-sm text-on-surface outline-none"
          >
            {CURRENCIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <NumericInput
            value={value.credit_limit}
            onChange={(next) => update("credit_limit", next)}
            placeholder="0.00"
            className="flex-1"
          />
        </div>
      </label>

      <label className="block sm:col-span-2">
        <span className="mb-1 block text-sm font-medium text-on-surface">
          {t("contacts.notes")}
        </span>
        <textarea
          value={value.notes}
          onChange={(e) => update("notes", e.target.value)}
          placeholder={t("contacts.notesPlaceholder")}
          rows={3}
          className="w-full rounded-xl border border-glass-border bg-glass-surface p-3 text-base text-on-surface shadow-sm outline-none backdrop-blur-md focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 md:text-sm"
        />
      </label>
    </div>
  );
}