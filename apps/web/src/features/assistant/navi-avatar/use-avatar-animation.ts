import { useEffect, useMemo, useState } from "react";

import type {
  AvatarDefinition,
  AnimationKey,
  ExpressionKey,
} from "./types";

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

const DEFAULT_TRANSITION_MS = 500;

interface UseAvatarAnimationOptions {
  definition: AvatarDefinition;
  animation?: AnimationKey;
  expression?: ExpressionKey;
  /** Render estático (sin parpadeo ni timeline). */
  static?: boolean;
}

export interface AvatarPlaybackState {
  animation?: AnimationKey;
  expression: ExpressionKey;
}

interface AvatarAnimationState {
  expression: ExpressionKey;
  blink: boolean;
  transitionMs: number;
}

function randomBetween(min: number, max: number): number {
  return min + Math.random() * (max - min);
}

/**
 * Motor de animación del avatar de Navi. Reproduce el timeline de una
 * animación (steps con `holdMs`/`transitionMs` en loop), programa el
 * parpadeo automático con los intervalos aleatorios de la definición y
 * respeta `prefers-reduced-motion` (deja el rostro en `neutral`).
 */
export function useAvatarAnimation({
  definition,
  animation,
  expression,
  static: isStatic,
}: UseAvatarAnimationOptions): AvatarAnimationState {
  const reducedMotion = useMemo(
    () => window.matchMedia(REDUCED_MOTION_QUERY).matches,
    [],
  );
  const mode: "animation" | "expression" | "static" =
    isStatic || reducedMotion ? "static" : animation ? "animation" : "expression";

  const [state, setState] = useState<AvatarAnimationState>(() => ({
    expression: (expression ?? "neutral") as ExpressionKey,
    blink: false,
    transitionMs: DEFAULT_TRANSITION_MS,
  }));

  // Timeline de pasos para `animation` (playbackMode loop).
  useEffect(() => {
    if (mode !== "animation" || !animation) return;
    const anim = definition.animations[animation];
    if (!anim || anim.steps.length === 0) return;

    let cancelled = false;
    let timeout: number;
    let index = 0;

    const advance = () => {
      if (cancelled) return;
      const step = anim.steps[index % anim.steps.length];
      setState((prev) => ({
        ...prev,
        expression: step.expression as ExpressionKey,
        transitionMs: step.transitionMs,
      }));
      index += 1;
      timeout = window.setTimeout(
        advance,
        step.transitionMs + step.holdMs,
      );
    };
    advance();

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [mode, animation, definition]);

  // Expresión controlada directamente (sin timeline).
  useEffect(() => {
    if (mode !== "expression" || !expression) return;
    setState((prev) => ({ ...prev, expression, transitionMs: DEFAULT_TRANSITION_MS }));
  }, [mode, expression]);

  // Ruta estática/reduced-motion: rostro fijo en neutral.
  useEffect(() => {
    if (mode !== "static") return;
    setState({ expression: "neutral" as ExpressionKey, blink: false, transitionMs: 0 });
  }, [mode]);

  // Parpadeo automático con los intervalos de la definición activa.
  useEffect(() => {
    if (mode === "static") return;
    const blinkCfg =
      (animation ? definition.animations[animation]?.blink : definition.animations.idle?.blink) ??
      { enabled: false, initialDelayMs: 0, minIntervalMs: 0, maxIntervalMs: 0, durationMs: 200 };
    if (!blinkCfg.enabled) {
      setState((prev) => ({ ...prev, blink: false }));
      return;
    }

    let cancelled = false;
    let waitTimeout: number;
    let blinkTimeout: number;

    const scheduleWait = (delay: number) => {
      waitTimeout = window.setTimeout(() => {
        if (cancelled) return;
        setState((prev) => ({ ...prev, blink: true }));
        blinkTimeout = window.setTimeout(() => {
          if (cancelled) return;
          setState((prev) => ({ ...prev, blink: false }));
          scheduleWait(randomBetween(blinkCfg.minIntervalMs, blinkCfg.maxIntervalMs));
        }, blinkCfg.durationMs);
      }, delay);
    };

    scheduleWait(blinkCfg.initialDelayMs);
    return () => {
      cancelled = true;
      window.clearTimeout(waitTimeout);
      window.clearTimeout(blinkTimeout);
    };
  }, [mode, animation, definition]);

  return state;
}