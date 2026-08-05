import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { LogIn } from "lucide-react";

import { api, ApiErrorClass, setAccessToken } from "@/lib/api";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const login = useMutation({
    mutationFn: () =>
      api.post<{ access: string }>("/auth/login", { email, password }),
    onSuccess: (data) => {
      setAccessToken(data.access);
      navigate("/");
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) setError(err.message);
      else setError(t("errors.generic"));
    },
  });

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
    </div>
  );
}