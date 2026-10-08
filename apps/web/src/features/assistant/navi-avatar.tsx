import { cn } from "@/lib/utils";
import { NaviAvatarView } from "@/features/assistant/navi-avatar/navi-avatar-view";
import { useAvatarAnimation } from "@/features/assistant/navi-avatar/use-avatar-animation";
import type {
  AnimationKey,
  AvatarDefinition,
} from "@/features/assistant/navi-avatar/types";
import naviAvatarJson from "@/features/assistant/navi-avatar/navi.avatar.json";

const definition = naviAvatarJson as unknown as AvatarDefinition;

interface NaviAvatarProps {
  size?: number;
  /** Mientras "escribe/piensa" se reproduce la animación "thinking". */
  thinking?: boolean;
  /** Sin animación de parpadeo (avatar estático). */
  static?: boolean;
  /** Animación explícita (tiene prioridad sobre `thinking`). */
  animation?: AnimationKey;
  className?: string;
}

/**
 * Rostro de "Navi": orbe con ojos alargados renderizado desde la definición
 * animada. `thinking` reproduce la animación de pensar; en otro caso `idle`.
 * Compartido entre la burbuja flotante, el chat y la interfaz de voz.
 */
export function NaviAvatar({
  size = 48,
  thinking = false,
  static: isStatic = false,
  animation,
  className,
}: NaviAvatarProps) {
  const { expression, blink, transitionMs } = useAvatarAnimation({
    definition,
    animation: animation ?? (thinking ? "thinking" : "searching"),
    static: isStatic,
  });

  return (
    <div
      className={cn(
        "clip-rounded-full relative overflow-hidden rounded-full border border-white/30 bg-white/25 backdrop-blur-md",
        className,
      )}
      style={{
        width: size,
        height: size,
      }}
    >
      <NaviAvatarView
        definition={definition}
        expression={expression}
        blink={blink}
        transitionMs={transitionMs}
        size={size}
      />
    </div>
  );
}