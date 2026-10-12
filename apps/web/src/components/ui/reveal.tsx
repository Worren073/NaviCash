import { motion, useReducedMotion, type HTMLMotionProps } from "motion/react";
import type { ReactNode } from "react";

interface RevealProps extends Omit<HTMLMotionProps<"div">, "initial" | "whileInView"> {
  children: ReactNode;
  delay?: number;
  duration?: number;
  y?: number;
}

export function Reveal({
  children,
  delay = 0,
  duration = 0.6,
  y = 16,
  ...props
}: RevealProps) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "0px 0px -12% 0px" }}
      transition={{ duration: reduce ? 0 : duration, ease: "easeOut", delay: reduce ? 0 : delay }}
      {...props}
    >
      {children}
    </motion.div>
  );
}