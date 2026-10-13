import { animate, useInView, useMotionValue, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

interface AnimatedNumberProps {
  /** Valor final al que debe llegar el conteo. */
  value: number;
  /** Formatea cada fotograma (p. ej. ``formatMoney``). */
  format: (value: number) => string;
  /** Duración total del conteo en segundos. */
  duration?: number;
  /** Retardo antes de arrancar (para escalonar varias cifras). */
  delay?: number;
  className?: string;
}

/**
 * Cifra que "sube" de 0 a su valor cuando entra en pantalla.
 *
 * El arranque se dispara con ``useInView`` (una sola vez) para que el conteo
 * ocurra justo cuando la tarjeta aparece. Con ``prefers-reduced-motion`` se
 * muestra el valor final sin animar. El formateador vive en un ``ref`` para
 * que un callback inline nuevo en cada render no re-dispare la animación.
 */
export function AnimatedNumber({
  value,
  format,
  duration = 1.2,
  delay = 0,
  className,
}: AnimatedNumberProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.4 });
  const reduce = useReducedMotion();
  const motionValue = useMotionValue(0);
  const formatRef = useRef(format);
  const [display, setDisplay] = useState(() => format(0));

  useEffect(() => {
    formatRef.current = format;
  });

  useEffect(() => {
    if (!inView) return;
    if (reduce) {
      setDisplay(formatRef.current(value));
      return;
    }
    const controls = animate(motionValue, value, {
      duration,
      delay,
      ease: "easeOut",
      onUpdate: (latest) => setDisplay(formatRef.current(latest)),
    });
    return () => controls.stop();
  }, [inView, reduce, value, duration, delay, motionValue]);

  return (
    <span ref={ref} className={className}>
      {display}
    </span>
  );
}
