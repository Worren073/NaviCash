import { Input } from "@/components/ui/input";
import {
  DEFAULT_MAX_DECIMALS,
  numericPattern,
  sanitizeNumeric,
  type NumericMode,
} from "@/lib/number";

/**
 * Input numérico que funciona con cualquier teclado del dispositivo.
 *
 * El teclado virtual muestra coma o punto según la regional del sistema y eso
 * no se puede forzar; por eso este componente usa ``type="text"`` + la
 * ``inputMode`` adecuada y normaliza el valor con ``sanitizeNumeric`` antes de
 * entregarlo al estado. El consumidor recibe SIEMPRE punto decimal.
 *
 * - ``mode="decimal"`` (default): dinero, stock, montos → teclado decimal
 * - ``mode="integer"``: días, cantidades enteras → sin tecla decimal
 * - ``mode="signed-*"``: admite ``-`` inicial (p. ej. ajuste de inventario)
 * - ``maxDecimals``: acota decimales (default 2; las tasas usan 4)
 *
 * Mantiene todas las props de ``Input`` (``required``, ``autoFocus``,
 * ``aria-invalid``, ``disabled``, ``className``, …). El ``pattern`` exportado
 * conserva la validación nativa que se perdía con ``type="number"``.
 */
export function NumericInput({
  mode = "decimal",
  maxDecimals = DEFAULT_MAX_DECIMALS,
  value,
  onChange,
  ...props
}: Omit<React.ComponentProps<typeof Input>, "type" | "value" | "onChange"> & {
  mode?: NumericMode;
  maxDecimals?: number;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <Input
      type="text"
      inputMode={isIntegerMode(mode) ? "numeric" : "decimal"}
      pattern={numericPattern(mode, maxDecimals)}
      value={value}
      onChange={(event) => onChange(sanitizeNumeric(event.target.value, mode, maxDecimals))}
      {...props}
    />
  );
}

function isIntegerMode(mode: NumericMode): boolean {
  return mode === "integer" || mode === "signed-integer";
}
