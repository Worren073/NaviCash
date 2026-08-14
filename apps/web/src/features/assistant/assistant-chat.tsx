import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { AnimatePresence, motion } from "motion/react";
import { Send, X, Mic } from "lucide-react";
import * as DialogPrimitive from "@radix-ui/react-dialog";

import { useAssistant } from "@/hooks/use-assistant";
import { NaviAvatar } from "@/features/assistant/navi-avatar";
import { useVoiceChat } from "@/features/assistant/voice-chat-context";
import { cn } from "@/lib/utils";

interface AssistantChatProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Panel de chat con "Navi" (Fase 1 del plan `docs/AI-ASSISTANT.md`).
 * Flotante, estilo liquid-glass, con historial de mensajes y entrada de texto.
 *
 * Accesibilidad (M11): role="dialog" + aria-modal + focus trap y cierre con
 * Escape a través de @radix-ui/react-dialog (incluye restaure de foco).
 */
export function AssistantChat({ open, onClose }: AssistantChatProps) {
  const { t } = useTranslation();
  const { messages, thinking, send } = useAssistant();
  const { openVoice } = useVoiceChat();
  const [draft, setDraft] = useState("");
  const listRef = useRef<HTMLDivElement>(null);

  // Autoscroll al fondo en cada mensaje.
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, thinking, open]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    void send(draft);
    setDraft("");
  }

  return (
    <DialogPrimitive.Root open={open} onOpenChange={(next) => { if (!next) onClose(); }}>
      <AnimatePresence>
        {open && (
          <DialogPrimitive.Portal forceMount>
            <DialogPrimitive.Content forceMount asChild aria-label={t("assistant.name")}>
              <motion.div
                initial={{ opacity: 0, y: 24, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 24, scale: 0.98 }}
                transition={{ type: "spring", stiffness: 320, damping: 30 }}
                className="clip-rounded-2xl fixed bottom-24 left-1/2 z-50 flex w-[calc(100%-2rem)] max-w-md -translate-x-1/2 flex-col overflow-hidden rounded-2xl border border-glass-border bg-white/60 shadow-[0_12px_40px_rgba(15,23,42,0.25)] backdrop-blur-2xl outline-none"
                style={{ maxHeight: "calc(100dvh - 8rem)" }}
              >
                <DialogPrimitive.Title className="sr-only">{t("assistant.name")}</DialogPrimitive.Title>

                {/* Cabecera */}
                <div className="flex items-center gap-3 border-b border-glass-border px-4 py-3">
                  <NaviAvatar size={40} thinking={thinking} />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold text-on-surface">{t("assistant.name")}</div>
                    <div className="flex items-center gap-1 text-xs text-on-surface-variant">
                      {thinking ? (
                        <>
                          {t("assistant.typing")}
                          <span className="animate-pulse">…</span>
                        </>
                      ) : (
                        <>
                          <span className="h-1.5 w-1.5 rounded-full bg-status-paid" />
                          {t("assistant.online")}
                        </>
                      )}
                    </div>
                  </div>
                  <button
                    type="button"
                    aria-label={t("common.close")}
                    onClick={onClose}
                    className="flex h-9 w-9 items-center justify-center rounded-full text-on-surface-variant transition-colors hover:bg-surface-container-high active:scale-95"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>

                {/* Aviso legal: Navi no es asesor financiero */}
                <div className="border-b border-glass-border bg-glass-surface px-4 py-2">
                  <p className="text-xs leading-snug text-on-surface-variant">{t("assistant.disclaimer")}</p>
                </div>

                {/* Mensajes */}
                <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
                  {messages.map((m) => (
                    <div
                      key={m.id}
                      className={cn(
                        "max-w-[85%] whitespace-pre-line rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
                        m.role === "user"
                          ? "ml-auto rounded-br-sm bg-primary text-on-primary shadow-sm"
                          : "mr-auto rounded-bl-sm bg-surface-container-high text-on-surface"
                      )}
                    >
                      {m.text}
                    </div>
                  ))}
                  {thinking && (
                    <div className="mr-auto flex items-center gap-1.5 rounded-2xl rounded-bl-sm bg-surface-container-high px-3.5 py-2.5">
                      {[0, 1, 2].map((i) => (
                        <motion.span
                          key={i}
                          className="h-1.5 w-1.5 rounded-full bg-on-surface-variant"
                          animate={{ opacity: [0.3, 1, 0.3] }}
                          transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }}
                        />
                      ))}
                    </div>
                  )}
                </div>

                {/* Entrada */}
                <form onSubmit={submit} className="flex items-center gap-2 border-t border-glass-border px-3 py-3">
                  <input
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    placeholder={t("assistant.placeholder")}
                    className="h-11 min-w-0 flex-1 rounded-xl border border-glass-border bg-glass-surface px-3 text-sm text-on-surface outline-none backdrop-blur-md transition-colors placeholder:text-on-surface-variant/70 focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30"
                    autoComplete="off"
                  />
                  <button
                    type="button"
                    onClick={() => {
                      onClose();
                      openVoice();
                    }}
                    aria-label={t("assistant.voice.title")}
                    className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-glass-border bg-glass-surface text-primary backdrop-blur-md transition-all hover:bg-surface-container-high active:scale-90"
                  >
                    <Mic className="h-5 w-5" />
                  </button>
                  <button
                    type="submit"
                    disabled={!draft.trim() || thinking}
                    aria-label={t("assistant.send")}
                    className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary text-on-primary shadow-sm transition-all hover:opacity-90 active:scale-90 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <Send className="h-5 w-5" />
                  </button>
                </form>
              </motion.div>
            </DialogPrimitive.Content>
          </DialogPrimitive.Portal>
        )}
      </AnimatePresence>
    </DialogPrimitive.Root>
  );
}