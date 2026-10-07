import type { CSSProperties } from "react";

import type {
  AvatarDefinition,
  ExpressionKey,
} from "./types";

interface NaviAvatarViewProps {
  definition: AvatarDefinition;
  expression: ExpressionKey;
  blink?: boolean;
  transitionMs?: number;
  size?: number;
}

const BASE = 135;

function at(size: number): number {
  return size / BASE;
}

/**
 * Cuerpo del avatar de Navi renderizado desde la definición: orbe con
 * degradado/brillo, cabeza con tilt 3D (`head.x/y/z`) y ojos con geometría,
 * ángulo y micro-movimiento por expresión. Las transiciones entre expresiones
 * usan `transitionMs`; el parpadeo aplica scaleY rápido por ojo.
 */
export function NaviAvatarView({
  definition,
  expression,
  blink = false,
  transitionMs = 500,
  size = 135,
}: NaviAvatarViewProps) {
  const expr =
    definition.expressions[expression] ?? definition.expressions["neutral"];
  const scale = at(size);
  const bodyColor = expr.colors?.body ?? definition.colors.body;
  const eyeColor = expr.colors?.eyes ?? definition.colors.eyes;

  const head = expr.head;
  const tilt: CSSProperties = {
    transform: `perspective(${size * 2.4}px) rotateX(${-head.y * 0.8}deg) rotateY(${head.x * 0.8}deg) rotateZ(${head.z * 0.7}deg) scale(${1 + -head.z / 700})`,
    transition: `transform ${transitionMs}ms ease`,
  };

  const bodyMotion = expr.motion?.body ?? "none";
  const eyeMotion = expr.motion?.eyes ?? "none";

  const motionStyle = (shake: string, drift: string): CSSProperties => {
    if (bodyMotion === "shake") return { animation: `${shake} 0.22s ease-in-out infinite` };
    if (bodyMotion === "slowDrift") return { animation: `${drift} 2.4s ease-in-out infinite` };
    return { animation: "none" };
  };

  const eyes = [
    { side: "left", g: expr.eyes.left, cx: -(expr.eyes.left.width + expr.eyes.spacing) / 2 },
    { side: "right", g: expr.eyes.right, cx: (expr.eyes.right.width + expr.eyes.spacing) / 2 },
  ] as const;

  return (
    <div
      className="relative overflow-hidden rounded-full"
      style={{
        width: size,
        height: size,
        background: bodyColor,
      }}
    >
      {/* Degradado de brillo tipo cristal sobre el orbe */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "linear-gradient(135deg, rgba(255,255,255,0.5) 0%, rgba(255,255,255,0.08) 42%, transparent 62%), radial-gradient(circle at 72% 82%, rgba(0,0,0,0.14) 0%, transparent 58%)",
        }}
      />

      {/* Capa de orientación de cabeza (tilt 2.5D) */}
      <div className="absolute inset-0" style={tilt}>
        {/* Micro-movimiento del cuerpo (shake / slowDrift) */}
        <div
          className="absolute inset-0"
          style={motionStyle("navi-head-shake", "navi-head-drift")}
        >
          {/* Micro-movimiento de ojos (shake) */}
          <div
            className="absolute inset-0"
            style={
              eyeMotion === "shake"
                ? { animation: "navi-eye-shake 0.24s ease-in-out infinite" }
                : { animation: "none" }
            }
          >
            {eyes.map(({ side, g, cx }) => {
              const centerX = size / 2 + cx * scale;
              const centerY = size / 2 + g.y * scale;
              return (
                <div
                  key={side}
                  className="absolute inset-0"
                  style={{
                    transform: `scaleY(${blink ? 0.12 : 1})`,
                    transformOrigin: `${centerX}px ${centerY}px`,
                    transition: "transform 120ms ease-out",
                  }}
                >
                  <div
                    className="absolute rounded-full"
                    style={{
                      left: centerX,
                      top: centerY,
                      width: g.width * scale,
                      height: g.height * scale,
                      background: eyeColor,
                      transform: `translate(-50%, -50%) rotate(${g.angle}deg)`,
                      transformOrigin: "center",
                      transition: `transform ${transitionMs}ms ease, left ${transitionMs}ms ease, top ${transitionMs}ms ease, width ${transitionMs}ms ease, height ${transitionMs}ms ease`,
                    }}
                  />
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}