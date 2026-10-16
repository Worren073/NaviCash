import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { sileo } from "sileo";
import {
  AlertCircle,
  ArrowLeft,
  Check,
  CheckCheck,
  FileText,
  MessageCircle,
  Paperclip,
  Search,
  Send,
  Settings,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Segmented } from "@/components/ui/segmented";
import {
  useChatConversations,
  useChatMessages,
  useInstagramConfig,
  useWhatsAppConfig,
  queryKeys,
} from "@/hooks/use-queries";
import { api, ApiErrorClass } from "@/lib/api";
import { formatDate, formatRelativeEvent } from "@/lib/format";
import type { ChatAttachment, ChatConversation, ChatMessage, ChatPlatform } from "@/lib/types";
import { WhatsAppConnectDialog } from "./whatsapp-connect-dialog";
import { InstagramConnectDialog } from "./instagram-connect-dialog";

/** Límite de tamaño aceptado por Instagram (imagen 8 MB; el resto 25 MB). */
const MAX_IMAGE_BYTES = 8 * 1024 * 1024;
const MAX_FILE_BYTES = 25 * 1024 * 1024;

/** Inicial visible en el avatar de una conversación. */
function avatarInitial(conversation: ChatConversation): string {
  const source = conversation.contact_name || conversation.external_id;
  return source.trim().charAt(0).toUpperCase() || "?";
}

/** Nombre a mostrar: el de la libreta, o el identificador si aún no tiene nombre. */
function displayName(conversation: ChatConversation): string {
  return conversation.contact_name || conversation.external_id;
}

/** Marca de estado de un mensaje saliente (enviado / entregado / leído/fallo). */
function StatusTick({ status }: { status: ChatMessage["status"] }) {
  if (status === "failed") return <AlertCircle className="h-3.5 w-3.5 text-error" />;
  if (status === "read") return <CheckCheck className="h-3.5 w-3.5 text-primary" />;
  if (status === "delivered") return <CheckCheck className="h-3.5 w-3.5" />;
  return <Check className="h-3.5 w-3.5" />;
}

/** Renderiza un adjunto según su tipo (imagen, video, audio o archivo). */
function AttachmentView({ attachment }: { attachment: ChatAttachment }) {
  const { t } = useTranslation();
  const { kind, url, filename } = attachment;

  if (kind === "image") {
    return (
      <a href={url} target="_blank" rel="noreferrer" className="block">
        <img
          src={url}
          alt={filename || t("chats.image")}
          className="max-h-64 w-full rounded-lg object-cover"
          loading="lazy"
        />
      </a>
    );
  }
  if (kind === "video") {
    return (
      <video src={url} controls className="max-h-64 w-full rounded-lg">
        <track kind="captions" />
      </video>
    );
  }
  if (kind === "audio") {
    return <audio src={url} controls className="w-full" />;
  }
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="flex items-center gap-2 rounded-lg bg-black/10 px-2 py-1.5 text-xs underline"
    >
      <FileText className="h-4 w-4 shrink-0" />
      <span className="truncate">{filename || t("chats.file")}</span>
    </a>
  );
}

function ConversationRow({
  conversation,
  active,
  onSelect,
}: {
  conversation: ChatConversation;
  active: boolean;
  onSelect: (c: ChatConversation) => void;
}) {
  const { t } = useTranslation();
  const hasUnread = conversation.unread_count > 0;
  return (
    <button
      type="button"
      onClick={() => onSelect(conversation)}
      className={`clip-rounded-lg flex w-full items-center gap-3 rounded-lg p-3 text-left transition-colors ${
        active ? "bg-primary/10" : "hover:bg-surface-container-high"
      }`}
    >
      <span className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full bg-primary/15 font-semibold text-primary">
        {conversation.avatar_url ? (
          <img
            src={conversation.avatar_url}
            alt=""
            className="h-10 w-10 object-cover"
            loading="lazy"
          />
        ) : (
          avatarInitial(conversation)
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center justify-between gap-2">
          <span className="truncate font-medium text-on-surface">
            {displayName(conversation)}
          </span>
          {conversation.last_message_at && (
            <span className="shrink-0 text-xs text-on-surface-variant">
              {formatRelativeEvent(conversation.last_message_at)}
            </span>
          )}
        </span>
        <span className="flex items-center justify-between gap-2">
          <span className="truncate text-sm text-on-surface-variant">
            {conversation.last_message_preview || t("chats.noMessages")}
          </span>
          {hasUnread && (
            <span className="flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full bg-primary px-1.5 text-xs font-semibold text-on-primary">
              {conversation.unread_count}
            </span>
          )}
        </span>
      </span>
    </button>
  );
}

export default function ChatsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [platform, setPlatform] = useState<ChatPlatform>("whatsapp");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [attachment, setAttachment] = useState<File | null>(null);
  const [connectOpen, setConnectOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const whatsappConfigQuery = useWhatsAppConfig();
  const instagramConfigQuery = useInstagramConfig();
  const configQuery = platform === "instagram" ? instagramConfigQuery : whatsappConfigQuery;
  const connected = Boolean(configQuery.data?.connected);

  // Al volver del OAuth de Instagram, avisa y limpia el parámetro de la URL.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const status = params.get("instagram");
    if (!status) return;
    if (status === "connected") {
      sileo.success({ title: t("chats.instagramDialog.success") });
      setPlatform("instagram");
      void queryClient.invalidateQueries({ queryKey: queryKeys.instagramConfig });
    } else if (status === "error") {
      sileo.error({ title: t("chats.instagramDialog.oauthError") });
    }
    params.delete("instagram");
    const query = params.toString();
    window.history.replaceState(
      {},
      "",
      `${window.location.pathname}${query ? `?${query}` : ""}`
    );
  }, [t, queryClient]);

  const conversationsQuery = useChatConversations(platform);
  const conversations = useMemo(
    () => conversationsQuery.data?.results ?? [],
    [conversationsQuery.data]
  );

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return conversations;
    return conversations.filter(
      (c) =>
        c.contact_name.toLowerCase().includes(term) ||
        c.external_id.toLowerCase().includes(term)
    );
  }, [conversations, search]);

  const selected = useMemo(
    () => conversations.find((c) => c.id === selectedId) ?? null,
    [conversations, selectedId]
  );

  const messagesQuery = useChatMessages(selectedId ?? undefined);
  const messages = useMemo(
    () => messagesQuery.data?.results ?? [],
    [messagesQuery.data]
  );

  // Al cambiar de plataforma se reinicia la selección y el borrador.
  const changePlatform = (next: ChatPlatform) => {
    setPlatform(next);
    setSelectedId(null);
    setDraft("");
    setAttachment(null);
  };

  // Al abrir un hilo, el backend marca como leído: refrescar también la lista
  // para que el contador de no leídos desaparezca de inmediato.
  const selectConversation = (conversation: ChatConversation) => {
    setSelectedId(conversation.id);
    setDraft("");
    setAttachment(null);
    void queryClient.invalidateQueries({ queryKey: queryKeys.chats });
  };

  // El thread hace scroll al último mensaje cuando llega uno nuevo.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, selectedId]);

  const send = useMutation({
    mutationFn: () => {
      if (attachment && platform === "instagram") {
        const form = new FormData();
        form.append("file", attachment);
        if (draft.trim()) form.append("text", draft.trim());
        return api.post<ChatMessage>(`/business/chats/${selectedId}/send/`, form);
      }
      return api.post<ChatMessage>(`/business/chats/${selectedId}/send/`, {
        text: draft.trim(),
      });
    },
    onSuccess: () => {
      setDraft("");
      setAttachment(null);
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.chatMessages }),
        queryClient.invalidateQueries({ queryKey: queryKeys.chats }),
      ]);
    },
    onError: (err) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("errors.generic");
      sileo.error({ title: msg });
    },
  });

  const pickAttachment = (file: File | null) => {
    if (!file) return;
    const isImage = file.type.startsWith("image/");
    const limit = isImage ? MAX_IMAGE_BYTES : MAX_FILE_BYTES;
    if (file.size > limit) {
      sileo.error({ title: t("chats.tooLarge", { mb: Math.floor(limit / (1024 * 1024)) }) });
      return;
    }
    setAttachment(file);
  };

  const hasContent = draft.trim().length > 0 || (Boolean(attachment) && platform === "instagram");
  const canSend = hasContent && !send.isPending;
  const platformLabel = t(
    platform === "instagram" ? "chats.platformInstagram" : "chats.platformWhatsApp"
  );

  return (
    <div className="mx-auto flex h-[calc(100vh-8rem)] max-w-6xl flex-col space-y-4">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
            <MessageCircle className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-on-surface">{t("chats.title")}</h1>
            <p className="text-sm text-on-surface-variant">{t("chats.subtitle")}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Segmented<ChatPlatform>
            layoutId="chats-platform"
            size="sm"
            value={platform}
            onChange={changePlatform}
            options={[
              { value: "whatsapp", label: t("chats.platformWhatsApp") },
              { value: "instagram", label: t("chats.platformInstagram") },
            ]}
          />
          <Badge variant={connected ? "secondary" : "outline"}>
            {connected ? t("chats.connected") : t("chats.disconnected")}
          </Badge>
          <Button variant="outline" className="gap-1" onClick={() => setConnectOpen(true)}>
            <Settings className="h-4 w-4" />
            {connected ? t("chats.settings") : t("chats.connect")}
          </Button>
        </div>
      </div>

      {!connected && !configQuery.isLoading && (
        <div className="glass-panel clip-rounded-lg rounded-lg p-4">
          <p className="font-medium text-on-surface">
            {t("chats.notConnectedTitle", { platform: platformLabel })}
          </p>
          <p className="mt-1 text-sm text-on-surface-variant">
            {t("chats.notConnectedHint", { platform: platformLabel })}
          </p>
          <Button variant="glow" className="mt-3 gap-1" onClick={() => setConnectOpen(true)}>
            <MessageCircle className="h-4 w-4" />
            {t("chats.connect")} {platformLabel}
          </Button>
        </div>
      )}

      <div className="grid min-h-0 flex-1 gap-4 md:grid-cols-[20rem_1fr]">
        {/* Panel de conversaciones: en móvil se oculta al abrir un hilo. */}
        <div
          className={`flex min-h-0 flex-col rounded-lg border border-glass-border bg-glass-surface/50 ${
            selected ? "hidden md:flex" : "flex"
          }`}
        >
          <div className="relative p-3">
            <Search className="absolute left-6 top-1/2 h-4 w-4 -translate-y-1/2 text-on-surface-variant" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("chats.searchPlaceholder")}
              className="pl-9"
              aria-label={t("chats.searchPlaceholder")}
            />
          </div>
          <div className="min-h-0 flex-1 space-y-1 overflow-y-auto px-2 pb-2">
            {conversationsQuery.isLoading ? (
              <>
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
              </>
            ) : conversationsQuery.isError ? (
              <p className="p-4 text-center text-sm text-on-surface-variant">
                {t("chats.loadError")}
              </p>
            ) : filtered.length === 0 ? (
              <p className="p-4 text-center text-sm text-on-surface-variant">
                {search.trim() ? t("chats.searchEmpty") : t("chats.empty")}
              </p>
            ) : (
              filtered.map((c) => (
                <ConversationRow
                  key={c.id}
                  conversation={c}
                  active={c.id === selectedId}
                  onSelect={selectConversation}
                />
              ))
            )}
          </div>
        </div>

        {/* Panel del hilo: en móvil solo aparece con un hilo seleccionado. */}
        <div
          className={`flex min-h-0 flex-col rounded-lg border border-glass-border bg-glass-surface/50 ${
            selected ? "flex" : "hidden md:flex"
          }`}
        >
          {!selected ? (
            <div className="flex flex-1 items-center justify-center p-6 text-center text-sm text-on-surface-variant">
              {t("chats.emptyThread")}
            </div>
          ) : (
            <>
              <div className="flex items-center gap-3 border-b border-glass-border p-3">
                <Button
                  variant="ghost"
                  size="icon"
                  className="md:hidden"
                  onClick={() => setSelectedId(null)}
                  aria-label={t("chats.back")}
                >
                  <ArrowLeft className="h-4 w-4" />
                </Button>
                <span className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full bg-primary/15 font-semibold text-primary">
                  {selected.avatar_url ? (
                    <img
                      src={selected.avatar_url}
                      alt=""
                      className="h-9 w-9 object-cover"
                      loading="lazy"
                    />
                  ) : (
                    avatarInitial(selected)
                  )}
                </span>
                <div className="min-w-0">
                  <p className="truncate font-medium text-on-surface">
                    {displayName(selected)}
                  </p>
                  <p className="truncate text-xs text-on-surface-variant">
                    {selected.external_id}
                  </p>
                </div>
              </div>

              <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
                {messagesQuery.isLoading ? (
                  <>
                    <Skeleton className="h-12 w-2/3" />
                    <Skeleton className="ml-auto h-12 w-1/2" />
                    <Skeleton className="h-12 w-2/3" />
                  </>
                ) : messagesQuery.isError ? (
                  <p className="text-center text-sm text-on-surface-variant">
                    {t("chats.threadLoadError")}
                  </p>
                ) : messages.length === 0 ? (
                  <p className="text-center text-sm text-on-surface-variant">
                    {t("chats.noMessages")}
                  </p>
                ) : (
                  messages.map((m) => {
                    const out = m.direction === "out";
                    return (
                      <div
                        key={m.id}
                        className={`flex ${out ? "justify-end" : "justify-start"}`}
                      >
                        <div
                          className={`max-w-[80%] space-y-2 rounded-2xl px-3.5 py-2 text-sm shadow-sm ${
                            out
                              ? "bg-primary text-on-primary"
                              : "bg-surface-container text-on-surface"
                          }`}
                        >
                          {m.attachments.map((att) => (
                            <AttachmentView key={att.id} attachment={att} />
                          ))}
                          {m.body && (
                            <p className="whitespace-pre-wrap break-words">{m.body}</p>
                          )}
                          <span
                            className={`flex items-center justify-end gap-1 text-[11px] ${
                              out ? "text-on-primary/80" : "text-on-surface-variant"
                            }`}
                          >
                            {formatDate(m.created_at)}
                            {out && <StatusTick status={m.status} />}
                          </span>
                        </div>
                      </div>
                    );
                  })
                )}
                <div ref={messagesEndRef} />
              </div>

              <div className="border-t border-glass-border p-3">
                {connected ? (
                  <div className="space-y-2">
                    {attachment && (
                      <div className="flex items-center gap-2 rounded-xl border border-glass-border bg-glass-surface px-3 py-2 text-sm">
                        <Paperclip className="h-4 w-4 shrink-0 text-on-surface-variant" />
                        <span className="min-w-0 flex-1 truncate text-on-surface">
                          {attachment.name}
                        </span>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => setAttachment(null)}
                          aria-label={t("chats.removeAttachment")}
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </div>
                    )}
                    <div className="flex items-end gap-2">
                      {platform === "instagram" && (
                        <>
                          <input
                            ref={fileInputRef}
                            type="file"
                            className="hidden"
                            onChange={(e) => {
                              pickAttachment(e.target.files?.[0] ?? null);
                              e.target.value = "";
                            }}
                          />
                          <Button
                            variant="outline"
                            size="icon"
                            onClick={() => fileInputRef.current?.click()}
                            aria-label={t("chats.attach")}
                          >
                            <Paperclip className="h-4 w-4" />
                          </Button>
                        </>
                      )}
                      <textarea
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && !e.shiftKey) {
                            e.preventDefault();
                            if (canSend) send.mutate();
                          }
                        }}
                        rows={1}
                        placeholder={t("chats.messagePlaceholder")}
                        className="h-11 max-h-32 min-h-11 flex-1 resize-none rounded-xl border border-glass-border bg-glass-surface px-3 py-2.5 text-base text-on-surface shadow-sm outline-none backdrop-blur-md focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 md:text-sm"
                      />
                      <Button
                        variant="glow"
                        size="icon"
                        onClick={() => send.mutate()}
                        disabled={!canSend}
                        aria-label={t("chats.send")}
                      >
                        <Send className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ) : (
                  <p className="flex items-center gap-2 text-sm text-on-surface-variant">
                    <X className="h-4 w-4" />
                    {t("chats.notConnectedTitle", { platform: platformLabel })}
                  </p>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {platform === "whatsapp" ? (
        <WhatsAppConnectDialog
          open={connectOpen}
          onOpenChange={setConnectOpen}
          config={whatsappConfigQuery.data}
        />
      ) : (
        <InstagramConnectDialog
          open={connectOpen}
          onOpenChange={setConnectOpen}
          config={instagramConfigQuery.data}
        />
      )}
    </div>
  );
}
