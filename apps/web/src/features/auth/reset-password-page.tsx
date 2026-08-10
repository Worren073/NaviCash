import { useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { KeyRound } from "lucide-react";
import { useMutation } from "@tanstack/react-query";

import { ApiErrorClass, resetPassword } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FieldHint } from "@/components/ui/field-hint";

function passwordRules(pw: string) {
  return {
    length: pw.length >= 8,
    letter: /[A-Za-záéíóúÁÉÍÓÚñü]/.test(pw),
    number: /\d/.test(pw),
  };
}

export default function ResetPasswordPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");
  const email = searchParams.get("email");

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const rules = passwordRules(password);
  const passwordsMatch = confirmPassword !== "" && confirmPassword === password;
  const canSubmit = rules.length && rules.letter && rules.number && passwordsMatch;

  const reset = useMutation({
    mutationFn: () => resetPassword(token ?? "", email ?? "", password),
    onSuccess: () => navigate("/login"),
    onError: (err) => {
      if (err instanceof ApiErrorClass) setError(err.message);
      else setError(t("errors.generic"));
    },
  });

  if (!token || !email) {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center px-6">
        <div className="glass-panel-elevated w-full max-w-sm space-y-4 rounded-2xl p-6 text-center">
          <h2 className="text-xl font-semibold text-on-surface">{t("auth.resetInvalidLink")}</h2>
          <Link to="/forgot-password" className="block font-medium text-primary underline">
            {t("auth.forgotTitle")}
          </Link>
        </div>
      </div>
    );
  }

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
          reset.mutate();
        }}
      >
        <h2 className="flex items-center gap-2 text-xl font-semibold text-on-surface">
          <KeyRound className="h-5 w-5 text-primary" />
          {t("auth.resetTitle")}
        </h2>
        <p className="text-sm text-on-surface-variant">{t("auth.resetHint")}</p>

        <div className="space-y-1.5">
          <Label htmlFor="password">{t("auth.password")}</Label>
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="confirmPassword">{t("auth.confirmPassword")}</Label>
          <Input
            id="confirmPassword"
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
          />
        </div>

        {password !== "" && (
          <div className="space-y-1 rounded-lg bg-surface-container-high/40 p-2.5">
            <FieldHint ok={rules.length}>{t("auth.passwordHintLength")}</FieldHint>
            <FieldHint ok={rules.letter}>{t("auth.passwordHintLetter")}</FieldHint>
            <FieldHint ok={rules.number}>{t("auth.passwordHintNumber")}</FieldHint>
            <FieldHint ok={passwordsMatch}>
              {passwordsMatch ? t("auth.passwordMatch") : t("auth.passwordNoMatch")}
            </FieldHint>
          </div>
        )}

        {error && (
          <p className="rounded-lg bg-error-container/60 px-3 py-2 text-sm text-on-error-container">
            {error}
          </p>
        )}

        <Button type="submit" className="w-full" disabled={reset.isPending || !canSubmit}>
          {reset.isPending ? t("common.loading") : t("auth.resetSubmit")}
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