import { useEffect, useState } from "react";
import { useLocation, useNavigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { LogIn } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, ApiErrorClass, consumeSessionExpired, setAccessToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import LegalAcceptanceDialog from "@/features/legal/legal-acceptance-dialog";

export default function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Terms acceptance modal state
  const [termsOpen, setTermsOpen] = useState(false);
  const [needsReacceptance, setNeedsReacceptance] = useState(false);

  // A11 — aviso global de sesión expirada (flag consumido desde api.ts).
  useEffect(() => {
    if (consumeSessionExpired()) setNotice(t("auth.sessionExpired"));
  }, [t]);

  // Aviso de "cuenta creada" cuando se llega desde el registro (verificación off).
  useEffect(() => {
    const state = location.state as { registered?: boolean } | null;
    if (state?.registered) setNotice(t("auth.registered"));
  }, [location.state, t]);

  const login = useMutation({
    mutationFn: () =>
      api.post<{ access: string }>("/auth/login", { email, password }),
    onSuccess: (data) => {
      setAccessToken(data.access);
      // Tras el login se comprueba si el usuario debe volver a aceptar los términos.
      api
        .get<{
          needs_reacceptance: boolean;
        }>("/auth/legal-acceptance")
        .then((acceptance) => {
          if (acceptance.needs_reacceptance) {
            setNeedsReacceptance(true);
            setTermsOpen(true);
          } else {
            navigate("/");
          }
        })
        .catch(() => {
          // Si no se puede consultar la aceptación, se deja entrar sin modal.
          navigate("/");
        });
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) setError(err.message);
      else setError(t("errors.generic"));
    },
  });

  const acceptTerms = () => {
    api
      .post("/auth/accept-terms", { accepted: true })
      .then(() => {
        setTermsOpen(false);
        void queryClient.invalidateQueries({
          queryKey: ["legal", "acceptance"],
        });
        navigate("/");
      })
      .catch((err) => {
        if (err instanceof ApiErrorClass) setError(err.message);
        else setError(t("errors.generic"));
      });
  };

  const declineTerms = async () => {
    try {
      await api.post("/auth/logout");
    } catch {
      // Se ignora: el cierre de sesión local basta.
    }
    setAccessToken(null);
    queryClient.clear();
    setError(t("auth.termsDeclinedLogout"));
    setTermsOpen(false);
  };

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-6">
      <div className="mb-8 flex flex-col items-center gap-2">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary text-2xl font-bold text-white shadow-lg shadow-primary/30">
          N
        </div>
        <h1 className="text-3xl font-bold tracking-tight text-on-surface">NaviCash</h1>
      </div>

      <form
        className="glass-panel-elevated w-full max-w-sm space-y-4 rounded-2xl p-6"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          setNotice(null);
          login.mutate();
        }}
      >
        <h2 className="text-xl font-semibold text-on-surface">{t("auth.loginTitle")}</h2>

        <div className="space-y-1.5">
          <Label htmlFor="email">{t("auth.email")}</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="password">{t("auth.password")}</Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>

        <div className="flex justify-end">
          <Link to="/forgot-password" className="text-sm font-medium text-primary underline">
            {t("auth.forgotPassword")}
          </Link>
        </div>

        {notice && (
          <p className="rounded-lg bg-income/10 px-3 py-2 text-sm text-income-text" role="status">
            {notice}
          </p>
        )}

        {error && (
          <p className="rounded-lg bg-error-container/60 px-3 py-2 text-sm text-on-error-container">
            {error}
          </p>
        )}

        <Button type="submit" className="w-full" disabled={login.isPending}>
          <LogIn />
          {login.isPending ? t("common.loading") : t("auth.login")}
        </Button>

        <p className="text-center text-sm text-on-surface-variant">
          {t("auth.registerTitle")}{" "}
          <Link to="/register" className="font-medium text-primary underline">
            {t("auth.register")}
          </Link>
        </p>
      </form>

      <LegalAcceptanceDialog
        open={termsOpen}
        onOpenChange={(open) => {
          // Si la re-aceptación es obligatoria, no se permite cerrar el modal
          // por ESC/clic fuera: el usuario debe aceptar o rechazar (logout).
          if (!open && needsReacceptance) return;
          setTermsOpen(open);
        }}
        onAccept={acceptTerms}
        onDecline={declineTerms}
        needsReacceptance={needsReacceptance}
      />
    </div>
  );
}