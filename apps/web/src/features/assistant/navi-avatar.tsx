import { useEffect, useState } from "react";
import { motion } from "motion/react";

import { cn } from "@/lib/utils";

interface NaviAvatarProps {
  size?: number;
  /** Mientras "escribe/piensa": los ojos miran arriba y parpadean seguido. */
  thinking?: boolean;
  /** Sin animación de parpadeo (avatar estático). */
  static?: boolean;
  className?: string;
}

/**
 * Rostro de "Navi": orbe translúcido con brillo azul superior-izquierdo y ojos
 * negros alargados (tipo palito). Compartido entre la burbuja flotante y el
 * chat. En estado `thinking` los ojos miran hacia arriba y parpadean.
 */
export function NaviAvatar({
  size = 48,
  thinking = false,
  static: isStatic = false,
  className,
}: NaviAvatarProps) {
  const [blink, setBlink] = useState(false);

  useEffect(() => {
    if (isStatic) return;
    let timeout: number | undefined;
    const blink = () => {
      setBlink(true);
      timeout = window.setTimeout(() => setBlink(false), 160);
    };
    const interval = setInterval(blink, thinking ? 1800 : 3200);
    return () => {
      clearInterval(interval);
      if (timeout !== undefined) clearTimeout(timeout);
    };
  }, [thinking, isStatic]);

  return (
    <div
      className={cn(
        "clip-rounded-full relative overflow-hidden rounded-full border border-white/30 bg-white/25 backdrop-blur-md",
        className
      )}
      style={{
        width: size,
        height: size,
      }}
    >
      {/* Brillo azul en todo el borde del orbe */}
      <span className="pointer-events-none absolute -left-1 -top-1 h-1/2 w-1/2 rounded-full bg-sky-400/40 blur-md" />
      <span className="pointer-events-none absolute -bottom-1 -left-1 h-1/2 w-1/2 rounded-full bg-sky-400/30 blur-md" />
      <span className="pointer-events-none absolute -right-1 -top-1 h-1/2 w-1/2 rounded-full bg-sky-400/30 blur-md" />
      <span className="pointer-events-none absolute -bottom-1 -right-1 h-1/2 w-1/2 rounded-full bg-sky-400/40 blur-md" />
      {/* Ojos */}
      <span className="pointer-events-none absolute inset-0 flex items-center justify-center gap-[22%]">
        <NaviEye blink={blink} thinking={thinking} />
        <NaviEye blink={blink} thinking={thinking} />
      </span>
    </div>
  );
}

function NaviEye({ blink, thinking }: { blink: boolean; thinking: boolean }) {
  return (
    <motion.span
      className="block h-[32%] w-[10%] rounded-full bg-black"
      animate={
        blink
          ? { scaleY: 0.2 }
          : { scaleY: 1, y: thinking ? -1.5 : 0 }
      }
      transition={{ type: "spring", stiffness: 400, damping: 25 }}
    />
  );
}