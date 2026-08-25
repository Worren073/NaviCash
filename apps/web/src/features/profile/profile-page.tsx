import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, BellRing, BrainCircuit, Trash2 } from "lucide-react";
import { LogoutIcon, SaveIcon, ListIcon, CheckedIcon } from "@/components/icons";

import { api, ApiErrorClass, setAccessToken } from "@/lib/api";
import {
  getPushState,
  subscribeToPush,
  unsubscribeFromPush,
  type PushState,
} from "@/lib/push";
import { queryKeys } from "@/hooks/use-queries";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import LegalAcceptanceDialog from "@/features/legal/legal-acceptance-dialog";
import { renderLegalMarkdown } from "@/features/legal/render-legal";
import type { User } from "@/lib/types";
import { cn } from "@/lib/utils";

interface LegalDocument {
  id: string;
  doc_type: "terms" | "privacy";
  version: string;
  title: string;
  content: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  effective_at: string | null;
}

interface LegalAcceptance {
  accepted_terms_at: string | null;
  accepted_terms_version: string;
  current_terms_version: string;
  needs_reacceptance: boolean;
}

/**
 * Tarjeta de Web Push: muestra el estado real (permiso, instalación iOS,
 * suscripción) y activa/desactiva con gesto de usuario, requisito de iOS
 * para poder pedir el permiso.
 */
function PushNotificationsCard() {
  const { t } = useTranslation();
  const [state, setState] = useState<PushState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getPushState()
      .then((s) => {
        if (alive) setState(s);
      })
      .catch(() => {
        if (alive) setState("unsupported");
      });
    return () => {
      alive = false;
    };
  }, []);

  const statusText =
    state === "on"
      ? t("profile.pushOn")
      : state === "off"
        ? t("profile.pushOff")
        : state === "denied"
          ? t("profile.pushDenied")
          : state === "needs-install"
            ? t("profile.pushNeedsInstall")
            : t("profile.pushUnsupported");

  const toggle = async () => {
    setError(null);
    setBusy(true);
    try {
      if (state === "on") await unsubscribeFromPush();
      else if (state === "off") await subscribeToPush();
      setState(await getPushState());
    } catch (err) {
      setError(err instanceof ApiErrorClass ? err.message : t("errors.generic"));
      setState(await getPushState().catch(() => "unsupported" as PushState));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="glass-panel clip-rounded-2xl space-y-3 rounded-2xl p-5">
      <h3 className="flex items-center gap-2 text-lg font-semibold text-on-surface">
        <BellRing className="h-5 w-5 text-primary" />
        {t("profile.pushTitle")}
      </h3>
      <p className="text-sm text-on-surface-variant">{t("profile.pushDesc")}</p>
      <p
        className={cn(
          "rounded-lg px-3 py-2 text-sm",
          state === "on"
            ? "bg-success-container/40 text-on-surface"
            : "bg-surface-container/60 text-on-surface-variant"
        )}
      >
        {statusText}
      </p>
      {(state === "on" || state === "off") && (
        <Button
          variant={state === "on" ? "outline" : "default"}
          className="w-full"
          onClick={() => void toggle()}
          disabled={busy || state === null}
        >
          {busy
            ? t("common.loading")
            : state === "on"
              ? t("profile.pushDisable")
              : t("profile.pushEnable")}
        </Button>
      )}
      {error && <p className="text-sm text-status-delayed">{error}</p>}
    </section>
  );
}

interface NaviMemory {
  id: string;
  clave: string;
  valor: string;
  fuente: "auto" | "usuario";
  usos: number;
  ultimo_uso: string;
}

function NaviMemoryCard() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [noteText, setNoteText] = useState("");

  const { data: memories = [], isLoading } = useQuery({
    queryKey: ["assistant", "memory"],
    queryFn: () => api.get<NaviMemory[]>("/assistant/memory"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/assistant/memory/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["assistant", "memory"] }),
  });

  const deleteAllMutation = useMutation({
    mutationFn: () => api.delete("/assistant/memory?all=1"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["assistant", "memory"] }),
  });

  const addMutation = useMutation({
    mutationFn: (texto: string) => api.post("/assistant/memory", { texto }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["assistant", "memory"] });
      setNoteText("");
    },
  });

  const formatKey = (k: string) => {
    if (k.startsWith("wallet_para:")) return k.replace("wallet_para:", "");
    if (k.startsWith("personalizado:")) return k.replace("personalizado:", "");
    if (k.startsWith("glosario:")) return k.replace("glosario:", "");
    return k;
  };

  return (
    <section className="glass-panel clip-rounded-2xl space-y-3 rounded-2xl p-5">
      <h3 className="flex items-center gap-2 text-lg font-semibold text-on-surface">
        <BrainCircuit className="h-5 w-5 text-primary" />
        {t("profile.navimemTitle")}
      </h3>
      <p className="text-sm text-on-surface-variant">{t("profile.navimemDesc")}</p>

      {isLoading ? (
        <Skeleton className="h-20 w-full" />
      ) : memories.length === 0 ? (
        <p className="rounded-lg bg-surface-container/60 px-3 py-2 text-sm text-on-surface-variant">
          {t("profile.navimemEmpty")}
        </p>
      ) : (
        <div className="space-y-2">
          {memories.map((m) => (
            <div
              key={m.id}
              className="flex items-center justify-between gap-2 rounded-lg bg-surface-container/40 px-3 py-2"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm text-on-surface">{formatKey(m.clave)}</p>
                <p className="truncate text-xs text-on-surface-variant">{m.valor}</p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-xs font-medium",
                    m.fuente === "auto"
                      ? "bg-primary/10 text-primary"
                      : "bg-secondary/10 text-secondary"
                  )}
                >
                  {m.usos}×
                </span>
                <button
                  type="button"
                  onClick={() => deleteMutation.mutate(m.id)}
                  className="rounded-full p-1 text-on-surface-variant hover:bg-error-container/40 hover:text-error"
                  aria-label={t("profile.navimemDelete")}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (noteText.trim().length >= 5) addMutation.mutate(noteText.trim());
        }}
        className="flex gap-2"
      >
        <Input
          type="text"
          placeholder={t("profile.navimemPlaceholder")}
          value={noteText}
          onChange={(e) => setNoteText(e.target.value)}
          className="flex-1"
          maxLength={200}
        />
        <Button
          type="submit"
          variant="outline"
          disabled={noteText.trim().length < 5 || addMutation.isPending}
        >
          {addMutation.isPending ? t("common.loading") : t("profile.navimemAdd")}
        </Button>
      </form>

      {memories.length > 0 && (
        <Button
          variant="ghost"
          className="w-full text-status-delayed hover:text-error"
          onClick={() => {
            if (window.confirm(t("profile.navimemClearConfirm"))) deleteAllMutation.mutate();
          }}
          disabled={deleteAllMutation.isPending}
        >
          {t("profile.navimemClear")}
        </Button>
      )}
    </section>
  );
}

export default function ProfilePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: me } = useQuery({
    queryKey: queryKeys.me,
    queryFn: () => api.get<User>("/auth/me"),
  });

  const { data: legalDocs } = useQuery({
    queryKey: ["legal", "documents"],
    queryFn: () => api.get<LegalDocument[]>("/legal"),
  });

  const { data: legalAcceptance } = useQuery({
    queryKey: ["legal", "acceptance"],
    queryFn: () => api.get<LegalAcceptance>("/auth/legal-acceptance"),
    enabled: !!me,
  });

  const [docDialogOpen, setDocDialogOpen] = useState(false);
  const [activeDoc, setActiveDoc] = useState<LegalDocument | null>(null);
  const [termsOpen, setTermsOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletePassword, setDeletePassword] = useState("");

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [reminderDays, setReminderDays] = useState("3");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const save = useMutation({
    mutationFn: () =>
      api.patch<User>("/auth/me", {
        first_name: firstName,
        last_name: lastName,
        phone,
        reminder_days: Number(reminderDays),
      }),
    onSuccess: () => {
      setSaved(true);
      void queryClient.invalidateQueries({ queryKey: queryKeys.me });
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) setError(err.message);
      else setError(t("errors.generic"));
    },
  });

  const logout = useMutation({
    mutationFn: () => api.post<{ detail: string }>("/auth/logout"),
    onSuccess: () => {
      setAccessToken(null);
      queryClient.clear();
      navigate("/login");
    },
  });

  const deleteAccount = useMutation({
    // El backend agenda la purga (15 días), revoca todas las sesiones y
    // limpia la cookie: aquí solo cerramos la sesión local y salimos.
    mutationFn: () =>
      api.post<{ detail: string; deletion_scheduled_at: string }>(
        "/auth/delete-account",
        { password: deletePassword },
      ),
    onSuccess: () => {
      setAccessToken(null);
      queryClient.clear();
      navigate("/login");
    },
  });

  useEffect(() => {
    if (me) {
      setFirstName(me.first_name ?? "");
      setLastName(me.last_name ?? "");
      setPhone(me.phone ?? "");
      setReminderDays(String(me.reminder_days ?? 3));
    }
  }, [me]);

  const openDoc = (doc: LegalDocument) => {
    setActiveDoc(doc);
    setDocDialogOpen(true);
  };

  const acceptTerms = useMutation({
    mutationFn: () =>
      api.post<{
        accepted_terms_at: string;
        accepted_terms_version: string;
      }>("/auth/accept-terms", { accepted: true }),
    onSuccess: () => {
      setTermsOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["legal", "acceptance"] });
    },
    onError: (err) => {
      setError(
        err instanceof ApiErrorClass ? err.message : t("errors.generic")
      );
    },
  });

  if (!me) {
    return (
      <>
        <div className="mt-4 space-y-6">
          <h2 className="text-3xl font-bold text-on-surface">{t("profile.title")}</h2>
          <div className="h-40 w-full">
            <Skeleton className="h-full w-full" />
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="mt-4 space-y-6">
        <h2 className="text-3xl font-bold text-on-surface">{t("profile.title")}</h2>
        <form
          className="glass-panel clip-rounded-2xl space-y-4 rounded-2xl p-5"
            onSubmit={(e) => {
              e.preventDefault();
              setSaved(false);
              setError(null);
              save.mutate();
            }}
          >
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="pfirst">{t("auth.firstName")}</Label>
                <Input
                  id="pfirst"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="plast">{t("auth.lastName")}</Label>
                <Input
                  id="plast"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="pphone">{t("auth.phone")}</Label>
              <Input
                id="pphone"
                type="tel"
                placeholder="+58 424 123 4567"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="pbase">{t("profile.baseCurrency")}</Label>
              <Input id="pbase" value={me.base_currency} readOnly />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="ptz">{t("profile.timezone")}</Label>
              <Input id="ptz" value={me.timezone_name} readOnly />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="premind">{t("profile.reminderDays")}</Label>
              <Input
                id="premind"
                type="number"
                min="0"
                max="30"
                value={reminderDays}
                onChange={(e) => setReminderDays(e.target.value)}
              />
            </div>

            {error && (
              <p className="rounded-lg bg-error-container/60 px-3 py-2 text-sm text-on-error-container">
                {error}
              </p>
            )}
            {saved && (
              <p className="rounded-lg bg-income/10 px-3 py-2 text-sm text-income">
                {t("profile.saved")}
              </p>
            )}

            <Button type="submit" className="w-full" disabled={save.isPending}>
              <SaveIcon size={16} /> {save.isPending ? t("common.loading") : t("profile.save")}
            </Button>
          </form>

          {/* Sección Legal */}
          <section className="glass-panel clip-rounded-2xl space-y-4 rounded-2xl p-5">
            <h3 className="text-lg font-semibold text-on-surface flex items-center gap-2">
              <ListIcon className="h-5 w-5" />
              {t("profile.legalTitle")}
            </h3>

            {legalDocs && (
              <div className="space-y-3">
                {legalDocs.map((doc) => (
                  <article
                    key={doc.id}
                    className="glass-panel-elevated clip-rounded-xl rounded-xl p-4 border border-glass-border"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <h4 className="font-semibold text-on-surface">{doc.title}</h4>
                          <span
                            className="px-3 py-1 text-sm rounded-full bg-primary/10 text-primary font-medium whitespace-nowrap shrink-0"
                          >
                            v{doc.version}
                          </span>
                          {legalAcceptance?.needs_reacceptance && doc.doc_type === "terms" && (
                            <span className="flex items-center gap-1 rounded-full bg-yellow-100 px-3 py-1 text-sm font-medium text-black whitespace-nowrap shrink-0">
                              <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                              {t("profile.legalUpdateRequired")}
                            </span>
                          )}
                        </div>
                        <p className="mt-1 text-sm text-on-surface-variant">
                          {t("profile.legalEffective")} {new Date(doc.effective_at ?? doc.created_at).toLocaleDateString()}
                        </p>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => openDoc(doc)}
                        className="shrink-0"
                      >
                        <ListIcon className="h-4 w-4 mr-1" />
                        {t("profile.legalView")}
                      </Button>
                    </div>
                  </article>
                ))}
              </div>
            )}

            {legalAcceptance && (
              <div className="pt-4 border-t border-glass-border">
                <h4 className="font-medium text-on-surface mb-3">{t("profile.legalAcceptanceTitle")}</h4>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-on-surface-variant">{t("profile.legalAcceptedAt")}</span>
                    <span className="text-on-surface font-medium">
                      {legalAcceptance.accepted_terms_at
                        ? new Date(legalAcceptance.accepted_terms_at).toLocaleDateString()
                        : t("profile.legalNotAccepted")}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-on-surface-variant">{t("profile.legalAcceptedVersion")}</span>
                    <span className="text-on-surface font-medium">
                      {legalAcceptance.accepted_terms_version || "—"}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-on-surface-variant">{t("profile.legalCurrentVersion")}</span>
                    <span className="text-on-surface font-medium">{legalAcceptance.current_terms_version}</span>
                  </div>
{legalAcceptance.needs_reacceptance && (
                    <div className="mt-3 rounded-lg border border-yellow-200 bg-yellow-50 p-3">
                      <p className="flex items-center gap-2 text-sm font-medium text-black">
                        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-yellow-100">
                          <CheckedIcon className="h-4 w-4" />
                        </span>
                        {t("profile.legalReacceptRequired")}
                      </p>
                      <Button
                        className="mt-3 w-full"
                        onClick={() => setTermsOpen(true)}
                        disabled={acceptTerms.isPending}
                      >
                        {acceptTerms.isPending
                          ? t("common.loading")
                          : t("profile.legalAcceptNow")}
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            )}
          </section>

          {/* Notificaciones push (Web Push + VAPID) */}
          <PushNotificationsCard />

          {/* Memoria del asistente Navi */}
          <NaviMemoryCard />

          {/* Zona de riesgo: eliminación de cuenta */}
          <section className="glass-panel clip-rounded-2xl space-y-3 rounded-2xl border border-error-container p-5">
            <h3 className="flex items-center gap-2 text-lg font-semibold text-on-surface">
              <AlertTriangle className="h-5 w-5 text-status-delayed" />
              {t("profile.dangerZoneTitle")}
            </h3>
            {me.deletion_scheduled_at ? (
              <p className="rounded-lg bg-error-container/40 px-3 py-2 text-sm text-on-error-container">
                {t("profile.deleteScheduledBanner", {
                  date: new Date(me.deletion_scheduled_at).toLocaleString(),
                })}
              </p>
            ) : (
              <p className="text-sm text-on-surface-variant">{t("profile.deleteWarning")}</p>
            )}
            <Button
              variant="destructive"
              className="w-full"
              disabled={deleteOpen || Boolean(me.deletion_scheduled_at)}
              onClick={() => {
                setDeletePassword("");
                setDeleteOpen(true);
              }}
            >
              {t("profile.deleteTitle")}
            </Button>
          </section>

          <Button
            variant="outline"
            className="w-full text-status-delayed"
            onClick={() => logout.mutate()}
            disabled={logout.isPending}
          >
            <LogoutIcon size={16} /> {logout.isPending ? t("common.loading") : t("auth.logout")}
          </Button>
      </div>

      {/* Confirmación de eliminación de cuenta */}
      <Dialog
        open={deleteOpen}
        onOpenChange={(open) => {
          if (!deleteAccount.isPending) setDeleteOpen(open);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("profile.deleteTitle")}</DialogTitle>
            <DialogDescription>{t("profile.deleteWarning")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="pdeletepw">{t("profile.deletePasswordLabel")}</Label>
            <Input
              id="pdeletepw"
              type="password"
              autoComplete="current-password"
              value={deletePassword}
              onChange={(e) => setDeletePassword(e.target.value)}
              disabled={deleteAccount.isPending}
            />
            {deleteAccount.isError && (
              <p className="rounded-lg bg-error-container/60 px-3 py-2 text-sm text-on-error-container">
                {deleteAccount.error instanceof ApiErrorClass
                  ? deleteAccount.error.message
                  : t("errors.generic")}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="ghost"
              onClick={() => setDeleteOpen(false)}
              disabled={deleteAccount.isPending}
            >
              {t("profile.deleteCancel")}
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteAccount.mutate()}
              disabled={deleteAccount.isPending || deletePassword.length === 0}
            >
              {deleteAccount.isPending ? t("common.loading") : t("profile.deleteConfirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={docDialogOpen} onOpenChange={setDocDialogOpen}>
        {activeDoc && (
          <DialogContent className="sm:max-w-2xl max-h-[80dvh]">
            <DialogHeader>
              <DialogTitle className="flex items-center justify-between">
                <span>{activeDoc.title}</span>
                <span className="px-2 py-0.5 text-xs rounded-full bg-primary/10 text-primary">
                  v{activeDoc.version}
                </span>
              </DialogTitle>
              <DialogDescription>
                {t("profile.legalEffective")} {new Date(activeDoc.effective_at ?? activeDoc.created_at).toLocaleDateString()}
              </DialogDescription>
            </DialogHeader>
            <div className="max-h-[55dvh] overflow-y-auto pr-1 prose prose-sm max-w-none text-on-surface-variant">
              {renderLegalMarkdown(activeDoc.content)}
            </div>
          </DialogContent>
        )}
      </Dialog>

      <LegalAcceptanceDialog
        open={termsOpen}
        onOpenChange={setTermsOpen}
        onAccept={() => acceptTerms.mutate()}
        needsReacceptance={Boolean(legalAcceptance?.needs_reacceptance)}
      />
    </>
  );
}