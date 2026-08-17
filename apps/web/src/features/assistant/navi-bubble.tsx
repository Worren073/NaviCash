import { cloneElement, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { motion, useMotionValue, useMotionValueEvent, useSpring } from "motion/react";

import { NaviAvatar } from "@/features/assistant/navi-avatar";
import { cn } from "@/lib/utils";

const BUBBLE_SIZE = 48;
const STORAGE_KEY = "navi.bubble.pos";
// Espacios reservados por las barras fijas del layout (TopBar ~68px abajo; el
// BottomNav ocupa desde vh-16 hacia arriba, dejando sitio para la burbuja).
const TOP_OFFSET = 72;
const BOTTOM_OFFSET = 96;

interface NaviBubbleProps {
  onOpen: () => void;
  /** Estado del chat para el "punto" de atención. */
  hasUnread?: boolean;
  /** Globo del tour guiado de Navi, anclado a la burbuja (hijo del wrapper). */
  tour?: React.ReactElement<{ side?: "left" | "right" }>;
}

/**
 * Burbuja flotante "Navi": un orbe translúcido con ojos que el usuario puede
 * arrastrar y soltar en cualquier lugar de la pantalla. Un click (sin arrastre)
 * abre el chat.
 *
 * La posición se persiste en localStorage (preferencia de UI, no dato sensible).
 *
 * El wrapper `fixed` mueve tanto la burbuja como el globo del tutorial anclado
 * (que se posiciona a la izquierda o derecha según el lado de la pantalla).
 *
 * En iOS, se aplican estilos adicionales para asegurar que la burbuja sea
 * perfectamente redonda (Safari tiene limitaciones con border-radius en
 * elementos position:fixed).
 */
export function NaviBubble({ onOpen, hasUnread = false, tour }: NaviBubbleProps) {
  const { t } = useTranslation();
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const springX = useSpring(x, { stiffness: 300, damping: 30 });
  const springY = useSpring(y, { stiffness: 300, damping: 30 });

  const [ready, setReady] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [side, setSide] = useState<"left" | "right">("right");

  const dragStart = useRef<{ px: number; py: number; dx: number; dy: number; moved: boolean } | null>(null);

  // Posición inicial: esquina inferior derecha, sobre el bottom nav.
  useEffect(() => {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let saved: { x: number; y: number } | null = null;
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) saved = JSON.parse(raw) as { x: number; y: number };
    } catch {
      saved = null;
    }
    const clampX = Math.min(Math.max(saved?.x ?? vw - BUBBLE_SIZE - 16, 8), vw - BUBBLE_SIZE - 8);
    const clampY = Math.min(
      Math.max(saved?.y ?? vh - BUBBLE_SIZE - BOTTOM_OFFSET, TOP_OFFSET),
      vh - BUBBLE_SIZE - BOTTOM_OFFSET,
    );
    x.set(clampX);
    y.set(clampY);
    setReady(true);
  }, [x, y]);

  // Lado de la pantalla donde está la burbuja → lado donde se ancla el globo.
  useMotionValueEvent(x, "change", (latest) => {
    setSide(latest < window.innerWidth / 2 ? "left" : "right");
  });

  function onPointerDown(e: React.PointerEvent<HTMLButtonElement>) {
    dragStart.current = { px: e.clientX, py: e.clientY, dx: x.get(), dy: y.get(), moved: false };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }

  function onPointerMove(e: React.PointerEvent<HTMLButtonElement>) {
    const s = dragStart.current;
    if (!s) return;
    const deltaX = e.clientX - s.px;
    const deltaY = e.clientY - s.py;
    if (Math.abs(deltaX) + Math.abs(deltaY) > 4) s.moved = true;
    if (!s.moved) return;

    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const nextX = Math.min(Math.max(s.dx + deltaX, 8), vw - BUBBLE_SIZE - 8);
    const nextY = Math.min(
      Math.max(s.dy + deltaY, TOP_OFFSET),
      vh - BUBBLE_SIZE - BOTTOM_OFFSET,
    );
    x.set(nextX);
    y.set(nextY);
    if (!dragging) setDragging(true);
  }

  function onPointerUp() {
    const s = dragStart.current;
    dragStart.current = null;
    setDragging(false);
    if (!s?.moved) {
      // Click sin arrastre → abrir el chat.
      onOpen();
      return;
    }
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ x: x.get(), y: y.get() }));
    } catch {
      // localStorage no disponible: no es crítico.
    }
  }

  return (
    <motion.div
      style={{ x: springX, y: springY }}
      className={cn("fixed left-0 top-0 z-40", ready ? "" : "opacity-0")}
    >
      <motion.button
        type="button"
        aria-label={t("assistant.openChat")}
        title={t("assistant.openChat")}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        style={{
          width: BUBBLE_SIZE,
          height: BUBBLE_SIZE,
          touchAction: "none",
          cursor: dragging ? "grabbing" : "grab",
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
