import { cloneElement, useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { motion, useMotionValue, useMotionValueEvent, useSpring } from "motion/react";

import { NaviAvatar } from "@/features/assistant/navi-avatar";
import { cn } from "@/lib/utils";

const BUBBLE_SIZE = 48;
const STORAGE_KEY = "navi.bubble.pos";
// Margen a los bordes al "pegarse" a la izquierda/derecha.
const EDGE_MARGIN = 8;
// Espacio reservado para que el BottomNav no tape la burbuja en móvil.
const BOTTOM_OFFSET = 96;
// Alto de la TopBar (móvil 3.125rem / desktop 3.5rem) + separación de 12px.
const TOPBAR_BOTTOM = { mobile: 50, desktop: 56 } as const;
const TOP_GAP = 12;

let cachedSafeTop: number | null = null;

/** Mide `env(safe-area-inset-top)` con una sonda de 1 elemento (se cachea). */
function getSafeAreaTop(): number {
  if (cachedSafeTop !== null) return cachedSafeTop;
  try {
    const probe = document.createElement("div");
    probe.style.cssText =
      "position:fixed;top:0;left:0;height:0;width:0;visibility:hidden;pointer-events:none;padding-top:env(safe-area-inset-top)";
    document.documentElement.appendChild(probe);
    cachedSafeTop = probe.getBoundingClientRect().height;
    probe.remove();
  } catch {
    cachedSafeTop = 0;
  }
  return cachedSafeTop;
}

/** Y inicial de la burbuja: justo debajo de la TopBar. */
function topOffset(isDesktop: boolean): number {
  const bar = isDesktop ? TOPBAR_BOTTOM.desktop : TOPBAR_BOTTOM.mobile;
  return getSafeAreaTop() + bar + TOP_GAP;
}

function clampY(vh: number, y: number): number {
  return Math.min(Math.max(y, topOffset(false)), vh - BUBBLE_SIZE - BOTTOM_OFFSET);
}

/** X "pegada" al borde (izquierda o derecha) más cercano a la posición dada. */
function snapX(vw: number, currentX?: number | null): number {
  const cursor = currentX ?? vw - BUBBLE_SIZE - EDGE_MARGIN;
  return cursor < vw / 2 ? EDGE_MARGIN : vw - BUBBLE_SIZE - EDGE_MARGIN;
}

interface NaviBubbleProps {
  onOpen: () => void;
  /** Estado del chat para el "punto" de atención. */
  hasUnread?: boolean;
  /** Globo del tour guiado de Navi, anclado a la burbuja (hijo del wrapper). */
  tour?: React.ReactElement<{ side?: "left" | "right" }>;
  /** Override de className del wrapper (p.ej. z-50 para mostrar sobre overlays). */
  wrapperClassName?: string;
  /**
   * Tour visible: la burbuja se pega automáticamente a la parte superior del
   * borde donde esté para que el globo de texto quede visible.
   */
  tourActive?: boolean;
}

/**
 * Burbuja flotante "Navi": un orbe translúcido con ojos que el usuario puede
 * arrastrar en móvil y soltar junto al borde (izquierda/derecha) más cercano.
 *
 * En desktop (lg+) queda FIJA en la parte superior derecha, justo debajo de la
 * TopBar, sin arrastre. En móvil la posición vertical se persiste en
 * localStorage (preferencia de UI, no dato sensible) y la horizontal siempre
 * se pega al borde más próximo.
 *
 * Si el tour está activo (`tourActive`), la burbuja sube sola a la parte
 * superior de su borde para no esconder el globo de texto.
 *
 * El wrapper `fixed` mueve tanto la burbuja como el globo del tutorial anclado
 * (que se posiciona a la izquierda o derecha según el lado de la pantalla).
 */
export function NaviBubble({ onOpen, hasUnread = false, tour, wrapperClassName, tourActive = false }: NaviBubbleProps) {
  const { t } = useTranslation();
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const springX = useSpring(x, { stiffness: 300, damping: 30 });
  const springY = useSpring(y, { stiffness: 300, damping: 30 });

  const [ready, setReady] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [side, setSide] = useState<"left" | "right">("right");
  const [isDesktop, setIsDesktop] = useState(
    () => window.matchMedia("(min-width: 1024px)").matches,
  );

  const dragStart = useRef<{
    px: number;
    py: number;
    dx: number;
    dy: number;
    moved: boolean;
  } | null>(null);

  // Detecta desktop (breakpoint lg) y se re-sincroniza al cambiar el viewport.
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const onChange = () => setIsDesktop(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  // Posición inicial: desktop fija arriba-derecha; móvil pegada al borde más
  // cercano (vertical libre y persistida).
  useEffect(() => {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    if (isDesktop) {
      x.set(vw - BUBBLE_SIZE - EDGE_MARGIN);
      y.set(topOffset(true));
    } else {
      let saved: { x: number; y: number } | null = null;
      try {
        const raw = window.localStorage.getItem(STORAGE_KEY);
        if (raw) saved = JSON.parse(raw) as { x: number; y: number };
      } catch {
        saved = null;
      }
      x.set(snapX(vw, saved?.x));
      y.set(clampY(vh, saved?.y ?? vh - BUBBLE_SIZE - BOTTOM_OFFSET));
    }
    setReady(true);
  }, [isDesktop, x, y]);

  // Al redimensionar la ventana, vuelve a pegar la burbuja a su borde.
  useEffect(() => {
    const onResize = () => {
      const vw = window.innerWidth;
      if (isDesktop) {
        x.set(vw - BUBBLE_SIZE - EDGE_MARGIN);
        y.set(topOffset(true));
      } else {
        x.set(snapX(vw, x.get()));
      }
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [isDesktop, x, y]);

  const persist = useCallback(() => {
    try {
      window.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ x: x.get(), y: y.get() }),
      );
    } catch {
      // localStorage no disponible: no es crítico.
    }
  }, [x, y]);

  // Tour activo → la burbuja sube sola a la parte superior de su borde para
  // que el globo de texto quede visible.
  useEffect(() => {
    if (!tourActive || !ready) return;
    const vw = window.innerWidth;
    x.set(isDesktop ? vw - BUBBLE_SIZE - EDGE_MARGIN : snapX(vw, x.get()));
    y.set(topOffset(isDesktop));
    if (!isDesktop) persist();
  }, [tourActive, ready, isDesktop, x, y, persist]);

  // Lado de la pantalla donde está la burbuja → lado donde se ancla el globo.
  useMotionValueEvent(x, "change", (latest) => {
    setSide(latest < window.innerWidth / 2 ? "left" : "right");
  });

  function onPointerDown(e: React.PointerEvent<HTMLButtonElement>) {
    if (isDesktop) return;
    dragStart.current = { px: e.clientX, py: e.clientY, dx: x.get(), dy: y.get(), moved: false };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }

  function onPointerMove(e: React.PointerEvent<HTMLButtonElement>) {
    if (isDesktop) return;
    const s = dragStart.current;
    if (!s) return;
    const deltaX = e.clientX - s.px;
    const deltaY = e.clientY - s.py;
    if (Math.abs(deltaX) + Math.abs(deltaY) > 4) s.moved = true;
    if (!s.moved) return;

    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const nextX = Math.min(Math.max(s.dx + deltaX, EDGE_MARGIN), vw - BUBBLE_SIZE - EDGE_MARGIN);
    x.set(nextX);
    y.set(clampY(vh, s.dy + deltaY));
    if (!dragging) setDragging(true);
  }

  function finishDrag(openChat: boolean) {
    const s = dragStart.current;
    dragStart.current = null;
    setDragging(false);
    if (isDesktop) {
      if (openChat) onOpen();
      return;
    }
    if (!s?.moved) {
      if (openChat) onOpen();
      return;
    }
    // Se pega al borde (izquierda/derecha) más cercano.
    x.set(snapX(window.innerWidth, x.get()));
    y.set(clampY(window.innerHeight, y.get()));
    persist();
  }

  function onPointerUp() {
    finishDrag(true);
  }

  function onPointerCancel() {
    finishDrag(false);
  }

  return (
    <motion.div
      style={{ x: springX, y: springY }}
      className={cn("fixed left-0 top-0 z-40", wrapperClassName, ready ? "" : "opacity-0")}
    >
      <motion.button
        type="button"
        aria-label={t("assistant.openChat")}
        title={t("assistant.openChat")}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerCancel}
        style={{
          width: BUBBLE_SIZE,
          height: BUBBLE_SIZE,
          touchAction: "none",
          cursor: isDesktop ? "default" : dragging ? "grabbing" : "grab",
        }}
        className="clip-rounded-full block rounded-full shadow-[0_6px_24px_rgba(0,106,97,0.25)] transition-shadow hover:shadow-[0_8px_32px_rgba(0,106,97,0.4)] active:scale-95"
      >
        <NaviAvatar size={BUBBLE_SIZE} />
        {/* Punto de atención si hay novedades */}
        {hasUnread && (
          <span className="absolute -right-0.5 -top-0.5 z-10 h-3 w-3 rounded-full bg-status-delayed ring-2 ring-white/60" />
        )}
      </motion.button>
      {tour ? cloneElement(tour, { side }) : null}
    </motion.div>
  );
}