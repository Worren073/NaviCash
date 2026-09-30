import { useId } from "react";

type Trend = "up" | "down";

interface TrendSparklineProps {
  trend: Trend;
  color: string;
  className?: string;
}

const UP_POINTS: ReadonlyArray<readonly [number, number]> = [
  [0, 26],
  [4, 23],
  [8, 24],
  [12, 17],
  [16, 20],
  [20, 12],
  [24, 16],
  [28, 9],
  [32, 13],
  [36, 6],
  [40, 10],
  [44, 4],
  [48, 8],
  [52, 3],
  [56, 6],
  [60, 3],
];

const DOWN_POINTS: ReadonlyArray<readonly [number, number]> = [
  [0, 4],
  [4, 7],
  [8, 5],
  [12, 12],
  [16, 8],
  [20, 15],
  [24, 11],
  [28, 18],
  [32, 14],
  [36, 21],
  [40, 17],
  [44, 24],
  [48, 20],
  [52, 26],
  [56, 23],
  [60, 27],
];

function smoothPath(points: ReadonlyArray<readonly [number, number]>): string {
  let d = `M ${points[0][0]} ${points[0][1]}`;
  for (let i = 1; i < points.length - 1; i += 1) {
    const [x0, y0] = points[i];
    const [x1, y1] = points[i + 1];
    const mx = (x0 + x1) / 2;
    const my = (y0 + y1) / 2;
    if (i === 1) {
      d += ` L ${points[1][0]} ${points[1][1]}`;
    }
    d += ` Q ${x0} ${y0} ${mx} ${my}`;
  }
  d += ` L ${points[points.length - 1][0]} ${points[points.length - 1][1]}`;
  return d;
}

export function TrendSparkline({ trend, color, className }: TrendSparklineProps) {
  const id = useId();
  const points = trend === "up" ? UP_POINTS : DOWN_POINTS;
  const line = smoothPath(points);
  const area = `${line} L 60 36 L 0 36 Z`;
  const uid = id.replace(/:/g, "");

  return (
    <svg
      viewBox="0 0 60 36"
      preserveAspectRatio="none"
      className={className}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={`trend-fill-${uid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
        <filter id={`trend-glow-${uid}`} x="-25%" y="-25%" width="150%" height="150%">
          <feGaussianBlur stdDeviation="2.2" />
        </filter>
      </defs>
      <path d={area} fill={`url(#trend-fill-${uid})`} />
      <path
        d={line}
        fill="none"
        stroke={color}
        strokeWidth={3}
        strokeLinecap="round"
        strokeLinejoin="round"
        filter={`url(#trend-glow-${uid})`}
        opacity={0.75}
      />
      <path
        d={line}
        fill="none"
        stroke={color}
        strokeWidth={1.75}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}