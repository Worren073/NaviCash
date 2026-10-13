import { motion, useReducedMotion } from "motion/react";
import { useId } from "react";

type Trend = "up" | "down";

interface TrendSparklineProps {
  trend: Trend;
  color: string;
  className?: string;
  /** Descubre la línea de izquierda a derecha al entrar en pantalla. */
  animate?: boolean;
}

// Tendencias suaves (pocas ondulaciones) para que la línea se lea como un
// trazo continuo, no como un zigzag. "up" sube (y baja) y "down" cae.
const UP_POINTS: ReadonlyArray<readonly [number, number]> = [
  [0, 28],
  [4, 26],
  [8, 25.5],
  [12, 23],
  [16, 23.5],
  [20, 20],
  [24, 20.5],
  [28, 17],
  [32, 17.5],
  [36, 14],
  [40, 14.5],
  [44, 11],
  [48, 11.5],
  [52, 8],
  [56, 8.5],
  [60, 5],
];

const DOWN_POINTS: ReadonlyArray<readonly [number, number]> = [
  [0, 6],
  [4, 8],
  [8, 8.5],
  [12, 11],
  [16, 10.5],
  [20, 14],
  [24, 13.5],
  [28, 17],
  [32, 16.5],
  [36, 20],
  [40, 19.5],
  [44, 23],
  [48, 22.5],
  [52, 26],
  [56, 25.5],
  [60, 29],
];

function round(value: number): number {
  return Math.round(value * 100) / 100;
}

/**
 * Interpolación Catmull-Rom → Bézier cúbica: genera un trazo **continuo y
 * suave** que pasa por todos los puntos (a diferencia de unir segmentos
 * rectos, que se vería quebrado).
 */
function smoothPath(points: ReadonlyArray<readonly [number, number]>): string {
  let d = `M ${points[0][0]} ${points[0][1]}`;
  for (let i = 0; i < points.length - 1; i += 1) {
    const p0 = points[i - 1] ?? points[i];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i + 2] ?? p2;
    const c1x = round(p1[0] + (p2[0] - p0[0]) / 6);
    const c1y = round(p1[1] + (p2[1] - p0[1]) / 6);
    const c2x = round(p2[0] - (p3[0] - p1[0]) / 6);
    const c2y = round(p2[1] - (p3[1] - p1[1]) / 6);
    d += ` C ${c1x} ${c1y} ${c2x} ${c2y} ${p2[0]} ${p2[1]}`;
  }
  return d;
}

export function TrendSparkline({ trend, color, className, animate = false }: TrendSparklineProps) {
  const id = useId();
  const reduce = useReducedMotion();
  const draw = animate && !reduce;
  const points = trend === "up" ? UP_POINTS : DOWN_POINTS;
  const line = smoothPath(points);
  const area = `${line} L 60 36 L 0 36 Z`;
  const uid = id.replace(/:/g, "");

  return (
    <motion.svg
      viewBox="0 0 60 36"
      preserveAspectRatio="none"
      className={className}
      aria-hidden="true"
      initial={draw ? "hidden" : false}
      whileInView={draw ? "show" : undefined}
      viewport={{ once: true, margin: "0px 0px -12% 0px" }}
    >
      <defs>
        <linearGradient id={`trend-fill-${uid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
        <filter id={`trend-glow-${uid}`} x="-25%" y="-25%" width="150%" height="150%">
          <feGaussianBlur stdDeviation="2.2" />
        </filter>
        {/* El rect crece de 0 a 60 (izquierda → derecha) para descubrir la línea. */}
        <clipPath id={`trend-clip-${uid}`}>
          <motion.rect
            x={0}
            y={0}
            width={60}
            height={36}
            variants={{
              hidden: { width: 0 },
              show: { width: 60, transition: { duration: 1.6, ease: "easeInOut" } },
            }}
          />
        </clipPath>
      </defs>
      <g clipPath={`url(#trend-clip-${uid})`}>
        <path d={area} fill={`url(#trend-fill-${uid})`} />
        <path
          d={line}
          fill="none"
          stroke={color}
          strokeWidth={3}
          strokeLinecap="round"
          strokeLinejoin="round"
          filter={`url(#trend-glow-${uid})`}
          opacity={0.7}
        />
        <path
          d={line}
          fill="none"
          stroke={color}
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </g>
    </motion.svg>
  );
}
