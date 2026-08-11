import { Fragment, type ReactNode } from "react";

/**
 * Renderer compartido de los documentos legales (términos y privacidad).
 *
 * Soporta el subconjunto de Markdown usado en `LegalDocument.content` y en
 * `legal-content.ts`, de modo que los modales de registro y de perfil pintan
 * exactamente el mismo texto sin marcas en crudo (sin asteriscos):
 *
 *   - Encabezados  `#` `##` `###` `####`
 *   - Encabezados por número de sección (ej. `1. Aceptación…`)
 *   - Negrita en línea  `**texto**`
 *   - Listas con viñeta  `- texto`
 *   - Tablas  `| a | b |`  con fila separadora opcional
 *   - Párrafos normales
 */

const BOLD_RE = /\*\*(.+?)\*\*/g;

/** Convierte la negrita ``**…**`` en línea a nodos ``<strong>``. */
function renderInline(text: string): ReactNode[] {
  const parts = text.split(BOLD_RE);
  return parts.map((part, i) =>
    i % 2 === 1 ? (
      <strong key={i} className="font-semibold text-on-surface">
        {part}
      </strong>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    )
  );
}

interface HeadingLevel {
  as: "h1" | "h2" | "h3" | "h4";
  size: string;
}

const HEADING_LEVELS: Record<string, HeadingLevel> = {
  "#": { as: "h1", size: "text-lg font-bold" },
  "##": { as: "h2", size: "text-base font-semibold" },
  "###": { as: "h3", size: "text-sm font-semibold" },
  "####": { as: "h4", size: "text-sm font-medium" },
};

/** Detecta un encabezado por marca `#`/`##`/…; si no, un encabezado de sección numerada. */
function headingInfo(block: string): { level: HeadingLevel; label: string } | null {
  const firstLine = block.trim();
  const mdMatch = /^(#{1,4})\s+(.+)$/.exec(firstLine);
  if (mdMatch) {
    const level = HEADING_LEVELS[mdMatch[1]];
    if (level) return { level, label: mdMatch[2] };
  }
  const numbered = /^(\d+)\.\s+(.+)$/.exec(firstLine);
  if (numbered && !block.includes("\n")) {
    const level = HEADING_LEVELS["##"];
    return { level, label: `${numbered[1]}. ${numbered[2]}` };
  }
  return null;
}

function Heading({ level, label }: { level: HeadingLevel; label: string }) {
  const Tag = level.as;
  return (
    <Tag className={`mb-2 mt-4 text-on-surface first:mt-0 ${level.size}`}>
      {label}
    </Tag>
  );
}

/** Devuelve true si un bloque entero es una línea en negrita `**…**`. */
function isBoldLine(text: string): boolean {
  const t = text.trim();
  return t.startsWith("**") && t.endsWith("**") && t.length > 4 && !t.includes("\n");
}

/** Convierte un bloque Markdown (separado por línea en blanco) a JSX. */
function renderBlock(block: string, blockIndex: number): ReactNode {
  const raw = block.trim();
  if (!raw) return null;

  const heading = headingInfo(raw);
  if (heading) {
    return <Heading key={blockIndex} level={heading.level} label={heading.label} />;
  }

  const lines = raw.split("\n");

  // Tabla: contiene filas con `|`.
  if (lines.some((line) => line.includes("|") && line.trim() !== "")) {
    const rows = lines
      .map((line) =>
        line
          .split("|")
          .map((cell) => cell.trim())
          .filter(Boolean)
      )
      .filter((row) => !(row.length === 1 && /^-{2,}$/.test(row[0])));
    return (
      <div key={blockIndex} className="mb-3 overflow-x-auto text-xs">
        <table className="min-w-full">
          <tbody>
            {rows.map((row, ri) => (
              <tr key={ri} className={ri === 0 ? "bg-surface-container-high" : ""}>
                {row.map((cell, ci) => (
                  <td key={ci} className="border border-glass-border px-2 py-1">
                    {renderInline(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  // Lista con viñetas: todas las líneas empiezan con "- ".
  if (lines.every((line) => line.trim().startsWith("- "))) {
    return (
      <ul key={blockIndex} className="mb-3 list-none space-y-1 pl-1">
        {lines.map((line, li) => (
          <li key={li} className="flex gap-2">
            <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-on-surface-variant" />
            <span>{renderInline(line.trim().replace(/^-\s+/, ""))}</span>
          </li>
        ))}
      </ul>
    );
  }

  // Línea entera en negrita (ej. advertencias).
  if (lines.length === 1 && isBoldLine(raw)) {
    return (
      <p key={blockIndex} className="mb-3 font-semibold text-on-surface">
        {renderInline(raw.slice(2, -2))}
      </p>
    );
  }

  return (
    <p key={blockIndex} className="mb-3">
      {renderInline(raw)}
    </p>
  );
}

/** Renderiza el cuerpo de un documento legal (Markdown) como nodos JSX. */
export function renderLegalMarkdown(body: string): ReactNode {
  const blocks = body.split(/\n\n+/);
  return blocks.map((block, i) => renderBlock(block, i));
}