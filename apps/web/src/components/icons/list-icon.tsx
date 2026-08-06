import { forwardRef, useImperativeHandle, useCallback } from "react";
import type { AnimatedIconHandle, AnimatedIconProps } from "./types";
import { motion, useAnimate } from "motion/react";

/** Icono de "lista/menú": tres barras que suben en cascada al animar. */
const ListIcon = forwardRef<AnimatedIconHandle, AnimatedIconProps>(
  (
    { size = 24, color = "currentColor", strokeWidth = 2, className = "" },
    ref,
  ) => {
    const [scope, animate] = useAnimate();

    const start = useCallback(async () => {
      await Promise.all([
        animate(".list-bar-1", { y: [0, -2, 0] }, { duration: 0.35, ease: "easeInOut" }),
        animate(
          ".list-bar-2",
          { y: [0, -2, 0] },
          { duration: 0.35, ease: "easeInOut", delay: 0.06 },
        ),
        animate(
          ".list-bar-3",
          { y: [0, -2, 0] },
          { duration: 0.35, ease: "easeInOut", delay: 0.12 },
        ),
      ]);
    }, [animate]);

    const stop = useCallback(() => {
      animate(".list-bar-1, .list-bar-2, .list-bar-3", { y: 0 }, { duration: 0.2 });
    }, [animate]);

    useImperativeHandle(ref, () => ({
      startAnimation: start,
      stopAnimation: stop,
    }));

    return (
      <motion.svg
        ref={scope}
        xmlns="http://www.w3.org/2000/svg"
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={`cursor-pointer ${className}`}
      >
        <motion.line className="list-bar-1" x1="4" y1="6" x2="20" y2="6" />
        <motion.line className="list-bar-2" x1="4" y1="12" x2="20" y2="12" />
        <motion.line className="list-bar-3" x1="4" y1="18" x2="14" y2="18" />
      </motion.svg>
    );
  },
);

ListIcon.displayName = "ListIcon";
export default ListIcon;