import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Mail } from "lucide-react";
import { useMutation } from "@tanstack/react-query";

import { ApiErrorClass, forgotPassword } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const EMAIL_RE = /^\S+@\S+\.\S+$/;

export default function ForgotPasswordPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const send = useMutation({
    mutationFn: () => forgotPassword(email),
    onSuccess: () => setSent(true),
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

      {sent ? (
        <div className="glass-panel-elevated w-full max-w-sm space-y-4 rounded-2xl p-6">
          <h2 className="flex items-center gap-2 text-xl font-semibold text-on-surface">
            <Mail className="h-5 w-5 text-primary" />
            {t("auth.forgotTitle")}
          </h2>
          <p className="text-sm leading-relaxed text-on-surface-variant">{t("auth.forgotSuccess")}</p>
          <Button className="w-full" variant="outline" onClick={() => navigate("/login")}>
            {t("auth.forgotBackToLogin")}
          </Button>
        </div>
      ) : (
        <form
          className="glass-panel-elevated w-full max-w-sm space-y-4 rounded-2xl p-6"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            if (!EMAIL_RE.test(email)) {
              setError(t("auth.forgotEmailInvalid"));
              return;
            }
            send.mutate();
          }}
        >
          <h2 className="flex items-center gap-2 text-xl font-semibold text-on-surface">
            <Mail className="h-5 w-5 text-primary" />
            {t("auth.forgotTitle")}
          </h2>
          <p className="text-sm text-on-surface-variant">{t("auth.forgotHint")}</p>

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

          {error && (
            <p className="rounded-lg bg-error-container/60 px-3 py-2 text-sm text-on-error-container">
              {error}
            </p>
          )}

          <Button type="submit" className="w-full" disabled={send.isPending}>
            {send.isPending ? t("common.loading") : t("auth.forgotSubmit")}
          </Button>

          <p className="text-center text-sm text-on-surface-variant">
            <Link to="/login" className="font-medium text-primary underline">
              {t("auth.forgotBackToLogin")}
            </Link>
          </p>
        </form>
      )}
    </div>
  );
}