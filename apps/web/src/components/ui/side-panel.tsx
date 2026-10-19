import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";

import { useMediaQuery } from "@/hooks/use-media-query";
import { cn } from "@/lib/utils";

function SidePanel(props: React.ComponentProps<typeof DialogPrimitive.Root>) {
  return <DialogPrimitive.Root data-slot="side-panel" {...props} />;
}

function SidePanelTrigger(props: React.ComponentProps<typeof DialogPrimitive.Trigger>) {
  return <DialogPrimitive.Trigger data-slot="side-panel-trigger" {...props} />;
}

function SidePanelClose(props: React.ComponentProps<typeof DialogPrimitive.Close>) {
  return <DialogPrimitive.Close data-slot="side-panel-close" {...props} />;
}

function SidePanelOverlay({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Overlay>) {
  return (
    <DialogPrimitive.Overlay
      data-slot="side-panel-overlay"
      className={cn(
        "fixed inset-0 z-50 bg-white/10 backdrop-blur-md data-[state=open]:animate-[fade-in_0.25s_ease-out] data-[state=closed]:animate-[fade-out_0.2s_ease-in] motion-reduce:animate-none",
        className
      )}
      {...props}
    />
  );
}

/**
 * Panel lateral responsive:
 * - Desktop (≥768px): se ancla al borde derecho y entra deslizando, cubriendo
 *   solo una franja de la pantalla con el fondo difuminado.
 * - Móvil: se comporta como un modal centrado normal.
 */
function SidePanelContent({
  className,
  size = "default",
  children,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content> & { size?: "default" | "wide" }) {
  const isDesktop = useMediaQuery("(min-width: 768px)");

  const width = size === "wide" ? "w-[720px]" : "w-[560px]";

  const desktop = `fixed right-0 top-0 z-50 flex h-dvh ${width} max-w-[92vw] flex-col gap-4 overflow-y-auto rounded-l-2xl border-l border-glass-border bg-white/80 p-6 shadow-[-8px_0_32px_rgba(15,23,42,0.25)] backdrop-blur-2xl data-[state=open]:animate-[panel-in-right_0.36s_cubic-bezier(0.22,1,0.36,1)] data-[state=closed]:animate-[panel-out-right_0.28s_ease-in] motion-reduce:animate-none`;

  const mobile =
    "fixed left-[50%] top-[50%] z-50 flex max-h-[85dvh] w-full max-w-[calc(100%-2rem)] flex-col gap-4 overflow-x-hidden overflow-y-auto rounded-2xl border border-glass-border bg-white/45 p-6 shadow-[0_8px_32px_rgba(15,23,42,0.25)] backdrop-blur-2xl data-[state=open]:animate-[panel-in-center_0.28s_ease-out] data-[state=closed]:animate-[panel-out-center_0.2s_ease-in] motion-reduce:animate-none";

  return (
    <DialogPrimitive.Portal>
      <SidePanelOverlay />
      <DialogPrimitive.Content
        data-slot="side-panel-content"
        className={cn(isDesktop ? desktop : mobile, className)}
        {...props}
      >
        {children}
        <DialogPrimitive.Close className="absolute right-4 top-4 rounded-full p-1 opacity-70 transition-opacity hover:opacity-100 focus:outline-none disabled:pointer-events-none">
          <X className="h-4 w-4" />
          <span className="sr-only">Cerrar</span>
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

function SidePanelHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="side-panel-header"
      className={cn("flex flex-col gap-1.5 text-left", className)}
      {...props}
    />
  );
}

function SidePanelFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="side-panel-footer"
      className={cn("mt-auto flex flex-col-reverse gap-2 sm:flex-row sm:justify-end", className)}
      {...props}
    />
  );
}

function SidePanelTitle({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Title>) {
  return (
    <DialogPrimitive.Title
      data-slot="side-panel-title"
      className={cn("text-lg font-semibold text-on-surface", className)}
      {...props}
    />
  );
}

function SidePanelDescription({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Description>) {
  return (
    <DialogPrimitive.Description
      data-slot="side-panel-description"
      className={cn("text-sm text-on-surface-variant", className)}
      {...props}
    />
  );
}

export {
  SidePanel,
  SidePanelClose,
  SidePanelContent,
  SidePanelDescription,
  SidePanelFooter,
  SidePanelHeader,
  SidePanelTitle,
  SidePanelTrigger,
};
