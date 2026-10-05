import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Segmented } from "@/components/ui/segmented";
import {
  TAX_ID_TYPES,
  formatTaxId,
  splitTaxId,
  taxIdFormatErrorKey,
  type TaxIdType,
} from "@/lib/tax-id";

const TYPE_HINTS: Record<TaxIdType, string> = {
  V: "taxId.hintV",
  J: "taxId.hintJ",
  E: "taxId.hintE",
};

export function TaxIdField({
  value,
  onChange,
  fixedType,
  id = "tax-id",
}: {
  value: string;
  onChange: (value: string) => void;
  /** Fija el tipo (V/J/E) cuando viene forzado desde otro flujo. */
  fixedType?: TaxIdType;
  id?: string;
}) {
  const { t } = useTranslation();
  const { type: parsedType, number } = splitTaxId(value);
  const type = fixedType ?? parsedType;
  const errorKey = taxIdFormatErrorKey(type, number);
  const numberId = `${id}-number`;

  return (
    <div>
      <span className="mb-1 block text-sm font-medium text-on-surface">Cédula / RIF</span>
      <Segmented<TaxIdType>
        options={TAX_ID_TYPES.map((value_) => ({ value: value_, label: value_ }))}
        value={type}
        onChange={(next) => onChange(formatTaxId(next, number))}
        layoutId={`tax-id-segmented-${id}`}
        size="sm"
        disabled={Boolean(fixedType)}
      />
      <div className="mt-2">
        <Input
          id={numberId}
          aria-label="Número de cédula"
          inputMode={type === "E" ? "text" : "numeric"}
          value={number}
          onChange={(e) => onChange(formatTaxId(type, e.target.value))}
          placeholder={type === "E" ? "A123456" : "12345678"}
        />
      </div>
      <span
        className={
          errorKey
            ? "mt-1 block text-xs text-destructive"
            : "mt-1 block text-xs text-on-surface-variant"
        }
      >
        {errorKey ? t(errorKey) : t(TYPE_HINTS[type])}
      </span>
    </div>
  );
}