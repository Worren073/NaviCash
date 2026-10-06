/**
 * Helpers para inputs numéricos.
 *
 * Motivo: el separador decimal del teclado virtual lo fija el sistema
 * operativo según la regional del dispositivo (es-ES/es-419 → coma) y la web
 * NO puede forzar el punto. Con ``type="number"`` el navegador descarta la
 * coma y el campo queda vacío, imposibilitando escribir decimales en esos
 * móviles. La solución es ``type="text"`` + ``inputMode="decimal"`` y
 * normalizar aquí: coma → punto, un solo punto y decimales acotados.
 *
 * Los límites coinciden con ``decimal_places`` del backend:
 * dinero/stock/cantidades = 2 (``MONEY_DECIMALS``), tasas manuales = 4.
 */

export type NumericMode = "decimal" | "integer" | "signed-decimal" | "signed-integer";

/** Decimales por defecto: idéntico al ``step="0.01"`` anterior. */
export const DEFAULT_MAX_DECIMALS = 2;

const isSigned = (mode: NumericMode): boolean =>
  mode === "signed-decimal" || mode === "signed-integer";

const isInteger = (mode: NumericMode): boolean => mode === "integer" || mode === "signed-integer";

/**
 * Patrón HTML del atributo ``pattern`` (full-match, como exige el navegador).
 *
 * Se pierde la validación nativa de ``min``/``step`` al salir de
 * ``type="number"``; este patrón recupera la de formato mientras que los
 * ``min`` se cubren con los guards del botón de submit en cada página.
 */
export function numericPattern(mode: NumericMode, maxDecimals: number = DEFAULT_MAX_DECIMALS): string {
  const sign = isSigned(mode) ? "-?" : "";
  if (isInteger(mode)) return `${sign}[0-9]*`;
  return `${sign}[0-9]*[.]?[0-9]{0,${maxDecimals}}`;
}

/**
 * Normaliza lo que el usuario teclea/pega para que el resto de la app (y el
 * backend) siempre reciban punto decimal.
 *
 * - coma → punto (el bug de teclados en regional es); letras, espacios y
 *   símbolos se descartan
 * - un solo punto: el primero gana, el resto se elimina ("1.2.3" → "1.23")
 * - acota los decimales a ``maxDecimals`` (evita el 400 de ``DecimalField``)
 * - enteros: corta en el primer punto ("3.7" → "3"), nunca fusiona dígitos
 * - negativos: el ``-`` solo se conserva al inicio
 */
export function sanitizeNumeric(
  raw: string,
  mode: NumericMode,
  maxDecimals: number = DEFAULT_MAX_DECIMALS
): string {
  let value = raw.trim();

  let sign = "";
  if (isSigned(mode) && value.startsWith("-")) {
    sign = "-";
    value = value.slice(1);
  }

  // La coma del teclado virtual es el separador decimal: hay que convertirla
  // a punto ANTES de depurar, si no "12,5" acabaría siendo "125".
  value = value.replace(/,/g, ".");
  value = value.replace(/[^0-9.]/g, "");

  if (isInteger(mode)) {
    const dot = value.indexOf(".");
    return sign + (dot === -1 ? value : value.slice(0, dot));
  }

  const firstDot = value.indexOf(".");
  if (firstDot !== -1) {
    value = value.slice(0, firstDot + 1) + value.slice(firstDot + 1).replace(/\./g, "");
  }
  const dot = value.indexOf(".");
  if (dot !== -1 && value.length - dot - 1 > maxDecimals) {
    value = value.slice(0, dot + 1 + maxDecimals);
  }
  return sign + value;
}

/**
 * Convierte a número para la lógica de presentación/cálculo.
 *
 * Acepta coma o punto por si acaso (estado previo a normalizar o valor
 * heredado), y devuelve 0 cuando no es interpretable — mismo contrato que el
 * ``Number(x) || 0`` que ya usaba la app.
 */
export function toNumber(raw: string, mode: NumericMode = "decimal"): number {
  const parsed = Number(sanitizeNumeric(raw, mode));
  return Number.isFinite(parsed) ? parsed : 0;
}
