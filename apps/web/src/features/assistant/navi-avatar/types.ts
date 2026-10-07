export interface AvatarExpression {
  head: {
    x: number;
    y: number;
    z: number;
  };
  eyes: {
    left: {
      width: number;
      height: number;
      x: number;
      y: number;
      angle: number;
    };
    right: {
      width: number;
      height: number;
      x: number;
      y: number;
      angle: number;
    };
    spacing: number;
  };
  perspective: number;
  motion?: {
    eyes?: "none" | "shake" | "slowDrift";
    body?: "none" | "shake" | "slowDrift";
  };
  colors?: {
    body?: string;
    eyes?: string;
  };
}

export interface AvatarAnimationStep {
  expression: string;
  holdMs: number;
  transitionMs: number;
  transition: "smooth";
}

export interface AvatarAnimation {
  playbackMode: "loop";
  steps: AvatarAnimationStep[];
  blink: {
    enabled: boolean;
    initialDelayMs: number;
    minIntervalMs: number;
    maxIntervalMs: number;
    durationMs: number;
  };
  metadata: {
    label: string;
    description: string;
    group?: string;
  };
}

export interface AvatarDefinition {
  schema: string;
  schemaVersion: number;
  name: string;
  body: {
    primary: {
      type: "sphere";
      width: number;
      height: number;
      depth: number;
      roundness: number;
    };
    nodes: unknown[];
  };
  colors: {
    body: string;
    eyes: string;
  };
  expressions: Record<string, AvatarExpression>;
  expressionOrder: string[];
  animations: Record<string, AvatarAnimation>;
  animationOrder: string[];
}

export type ExpressionKey = keyof AvatarDefinition["expressions"];
export type AnimationKey = keyof AvatarDefinition["animations"];