/**
 * tax-id — Cédula/RIF de clientes: prefijo de tipo (V, J, E) y número.
 *
 * Espejo de `services/api/apps/crm/tax_id.py`: la fuente de verdad es el
 * backend, estas funciones solo dan feedback inmediato en el formulario.
 * El valor canónico es `PREFIJO-NÚMERO` en mayúsculas (ej. `V-12345678`).
 */

export type TaxIdType = "V" | "J" | "E";

export const TAX_ID_TYPES: TaxIdType[] = ["V", "J", "E"];

const NUMBER_PATTERNS: Record<TaxIdType, RegExp> = {
  V: /^\d{6,8}$/,
  J: /^\d{9,11}$/,
  E: /^[A-Z0-9]{5,12}$/,
};

const TYPE_CODES: Record<TaxIdType, string> = { V: "V", J: "J", E: "E" };

export interface TaxIdParts {
  type: TaxIdType;
  number: string;
}

/** Separa un valor de cédula en tipo y número, ignorando espacios y guiones. */
export function splitTaxId(value: string): TaxIdParts {
  const cleaned = (value ?? "").toUpperCase().replace(/[\s._-]/g, "");
  const first = cleaned.charAt(0);
  const type = isTaxIdType(first) ? first : "V";
  return { type, number: cleaned.slice(1) };
}

function isTaxIdType(value: string): value is TaxIdType {
  return TAX_ID_TYPES.includes(value as TaxIdType);
}

/** Compone el valor canónico `PREFIJO-NÚMERO` (o vacío si no hay número). */
export function formatTaxId(type: TaxIdType, number: string): string {
  const clean = number.replace(/[\s._-]/g, "").toUpperCase();
  return clean ? `${TYPE_CODES[type]}-${clean}` : "";
}

/** Key de i18n con el mensaje de formato para el tipo dado, o null si es válido. */
export function taxIdFormatErrorKey(type: TaxIdType, number: string): string | null {
  if (!number) return null;
  return NUMBER_PATTERNS[type].test(number) ? null : `taxId.format.${type}`;
}

/** True si el documento tiene prefijo V/J/E y un número con el formato válido. */
export function isValidTaxId(value: string): boolean {
  const { type, number } = splitTaxId(value);
  if (!number) return false;
  return NUMBER_PATTERNS[type].test(number);
}

/** Texto de búsqueda: si hay dígitos, cédula canónica; si hay texto, se usa tal cual. */
export function taxIdSearchTerm(
  raw: string,
  type: TaxIdType,
): { term: string; hasDigits: boolean; number: string } {
  const clean = (raw ?? "").trim();
  const digits = clean.replace(/\D/g, "");
  if (digits) {
    return { term: formatTaxId(type, digits), hasDigits: true, number: digits };
  }
  return { term: clean, hasDigits: false, number: "" };
}