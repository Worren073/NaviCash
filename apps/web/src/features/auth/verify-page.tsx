import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation } from "@tanstack/react-query";
import { BadgeCheck } from "lucide-react";

import { api, ApiErrorClass } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface VerifyState {
  debugToken?: string;
  email?: string;
}

export default function VerifyPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state ?? {}) as VerifyState;
  const [searchParams] = useSearchParams();
  const urlToken = searchParams.get("token") ?? "";

  const [token, setToken] = useState(state.debugToken ?? urlToken);
  const [error, setError] = useState<string | null>(null);

  const verify = useMutation({
    mutationFn: () => api.post<{ detail: string }>("/auth/verify-email", { token }),
    onSuccess: async () => {
      navigate("/login");
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) setError(err.message);
      else setError(t("errors.generic"));
    },
  });

  // Si el enlace del correo trajo un token en la URL, auto-verifica al abrir.
  const autoVerified = useRef(false);
  useEffect(() => {
    if (urlToken && !autoVerified.current) {
      autoVerified.current = true;
      setError(null);
      verify.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlToken]);

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
          verify.mutate();
        }}
      >
        <h2 className="flex items-center gap-2 text-xl font-semibold text-on-surface">
          <BadgeCheck className="h-5 w-5 text-primary" />
          {t("auth.verifyTitle")}
        </h2>
        <p className="text-sm text-on-surface-variant">{t("auth.verifyHint")}</p>

        <div className="space-y-1.5">
          <Label htmlFor="token">{t("auth.verifyTitle")}</Label>
          <Input
            id="token"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="token-verificacion"
            required
          />
        </div>

        {error && (
          <p className="rounded-lg bg-error-container/60 px-3 py-2 text-sm text-on-error-container">
            {error}
          </p>
        )}

        <Button type="submit" className="w-full" disabled={verify.isPending}>
          {verify.isPending ? t("common.loading") : t("auth.verifyTitle")}
        </Button>

        <p className="text-center text-sm text-on-surface-variant">
          <Link to="/login" className="font-medium text-primary underline">
            {t("auth.login")}
          </Link>
        </p>
      </form>
    </div>
  );
}