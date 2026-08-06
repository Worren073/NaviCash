import { useEffect, useRef, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { UserPlus } from "lucide-react";
import { useMutation } from "@tanstack/react-query";

import { api, ApiErrorClass } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FieldHint } from "@/components/ui/field-hint";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";

const CAPTCHA_SITE_KEY = import.meta.env.VITE_CAPTCHA_SITE_KEY as string | undefined;

declare global {
  interface Window {
    turnstile?: {
      render: (
        container: HTMLElement,
        opts: { sitekey: string; callback: (token: string) => void; "expired-callback": () => void }
      ) => string;
      reset: (widgetId: string) => void;
      remove: (widgetId: string) => void;
    };
  }
}

function passwordRules(pw: string) {
  return {
    length: pw.length >= 8,
    letter: /[A-Za-záéíóúÁÉÍÓÚñü]/.test(pw),
    number: /\d/.test(pw),
  };
}

const TERMS_SECTIONS = [
  {
    title: "1. Servicio",
    body: "NaviCash es una herramienta de registro y seguimiento de tus finanzas personales. No almacenamos tus fondos ni realizamos movimientos de dinero: solo registras tus cobros y pagos para organizarte mejor.",
  },
  {
    title: "2. Cuenta",
    body: "Eres responsable de mantener confidenciales tu correo y contraseña. Aceptas recibir correos de verificación y notificaciones de vencimientos. Si detectas un uso no autorizado de tu cuenta, debes notificarnos de inmediato.",
  },
  {
    title: "3. Uso permitido",
    body: "Te comprometes a usar NaviCash únicamente con fines legales y legítimos. Queda prohibido su uso para actividades fraudulentas, lavado de dinero o cualquier actividad ilegal. Nos reservamos el derecho de suspender cuentas que incumplan estos términos.",
  },
  {
    title: "4. Datos y privacidad",
    body: "Tus datos (transacciones, saldos, contactos) son privados y solo se usan para ofrecerte el servicio. No vendemos ni compartimos tu información con terceros, salvo obligación legal. Puedes solicitar la eliminación de tu cuenta y de tus datos en cualquier momento.",
  },
  {
    title: "5. Disponibilidad",
    body: "El servicio se ofrece tal cual, sin garantías de disponibilidad ininterrumpida. Podemos introducir cambios, interrupciones por mantenimiento o suspender el servicio con aviso previo razonable.",
  },
  {
    title: "6. Limitación de responsabilidad",
    body: "NaviCash no es responsable de errores de cálculo, decisiones financieras tomadas con base en la información registrada, ni de daños indirectos derivados del uso del servicio. Los valores de la tasa BCV mostrados son referenciales.",
  },
  {
    title: "7. Modificaciones",
    body: "Podremos actualizar estos términos. Los cambios relevantes se te notificarán por correo, y la continuación del uso del servicio implicará la aceptación de la nueva versión, que quedará registrada en tu perfil.",
  },
  {
    title: "8. Contacto",
    body: "Para cualquier duda sobre estos términos o el tratamiento de tus datos, puedes escribirnos a soporte@navicash.app.",
  },
];

export default function RegisterPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [termsOpen, setTermsOpen] = useState(false);
  const [termsScrolled, setTermsScrolled] = useState(false);
  const [captchaToken, setCaptchaToken] = useState("");
  const [error, setError] = useState<string | null>(null);

  const turnstileRef = useRef<HTMLDivElement>(null);
  const widgetIdRef = useRef<string | null>(null);

  const rules = passwordRules(password);
  const passwordsMatch = confirmPassword !== "" && confirmPassword === password;
  const captchaRequired = Boolean(CAPTCHA_SITE_KEY);
  const captchaReady = !captchaRequired || captchaToken !== "";

  const canSubmit =
    rules.length &&
    rules.letter &&
    rules.number &&
    passwordsMatch &&
    termsAccepted &&
    captchaReady;

  // Carga el widget de Cloudflare Turnstile si hay site key configurada.
  useEffect(() => {
    if (!CAPTCHA_SITE_KEY || !turnstileRef.current) return;
    let disposed = false;

    const render = () => {
      if (!disposed && window.turnstile && turnstileRef.current) {
        widgetIdRef.current = window.turnstile.render(turnstileRef.current, {
          sitekey: CAPTCHA_SITE_KEY,
          callback: (token) => setCaptchaToken(token),
          "expired-callback": () => setCaptchaToken(""),
        });
      }
    };

    if (window.turnstile) {
      render();
    } else {
      const script = document.createElement("script");
      script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
      script.async = true;
      script.defer = true;
      script.onload = render;
      document.head.appendChild(script);
    }

    return () => {
      disposed = true;
      if (widgetIdRef.current && window.turnstile) {
        window.turnstile.remove(widgetIdRef.current);
      }
      widgetIdRef.current = null;
    };
  }, []);

  const register = useMutation({
    mutationFn: () =>
      api.post<{ detail: string; debug_token?: string }>("/auth/register", {
        first_name: firstName,
        last_name: lastName,
        email,
        phone,
        password,
        accepted_terms: true,
        captcha_token: captchaToken,
      }),
    onSuccess: (data) => {
      // En dev el backend devuelve el token para verificar sin correo real.
      navigate("/verify", { state: { debugToken: data.debug_token } });
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) {
        const field = err.fieldErrors ?? {};
        setError(
          field.email?.[0] ??
            field.password?.[0] ??
            field.phone?.[0] ??
            field.accepted_terms?.[0] ??
            field.captcha_token?.[0] ??
            err.message
        );
        if (field.captcha_token && widgetIdRef.current && window.turnstile) {
          window.turnstile.reset(widgetIdRef.current);
          setCaptchaToken("");
        }
      } else {
        setError(t("errors.generic"));
      }
    },
  });

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-6 py-8">
      <div className="mb-8 flex flex-col items-center gap-2">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary text-2xl font-bold text-white shadow-lg shadow-primary/30">
          N
        </div>
        <h1 className="text-3xl font-bold tracking-tight text-on-surface">NaviCash</h1>
      </div>

      <form
        className="glass-panel-elevated w-full max-w-md space-y-4 rounded-2xl p-6"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          register.mutate();
        }}
      >
        <h2 className="text-xl font-semibold text-on-surface">{t("auth.registerTitle")}</h2>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="firstName">{t("auth.firstName")}</Label>
            <Input
              id="firstName"
              autoComplete="given-name"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="lastName">{t("auth.lastName")}</Label>
            <Input
              id="lastName"
              autoComplete="family-name"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
            />
          </div>
        </div>

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
          <Label htmlFor="phone">{t("auth.phone")}</Label>
          <Input
            id="phone"
            type="tel"
            autoComplete="tel"
            placeholder={t("auth.phonePlaceholder")}
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
          {phone !== "" && (
            <FieldHint ok={/^\+?[\d\s()-]{7,20}$/.test(phone)}>{t("auth.phonePlaceholder")}</FieldHint>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3">
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

        <label
          className="flex cursor-pointer items-center gap-2.5 text-sm text-on-surface"
          onClick={(e) => {
            e.preventDefault();
            setTermsOpen(true);
          }}
        >
          <input
            type="checkbox"
            checked={termsAccepted}
            readOnly
            className="h-4 w-4 accent-primary"
          />
          <span>
            {t("auth.termsLabel")}{" "}
            <span className="font-medium text-primary underline">{t("auth.readTerms")}</span>
          </span>
        </label>

        {captchaRequired && (
          <div className="space-y-1.5">
            <div ref={turnstileRef} className="[&>div]:mx-auto" />
            {captchaToken === "" && (
              <FieldHint>{t("auth.captchaHint")}</FieldHint>
            )}
          </div>
        )}

        {error && (
          <p className="rounded-lg bg-error-container/60 px-3 py-2 text-sm text-on-error-container">
            {error}
          </p>
        )}

        <Button type="submit" className="w-full" disabled={register.isPending || !canSubmit}>
          <UserPlus />
          {register.isPending ? t("common.loading") : t("auth.register")}
        </Button>

        <p className="text-center text-sm text-on-surface-variant">
          {t("auth.loginTitle")}{" "}
          <Link to="/login" className="font-medium text-primary underline">
            {t("auth.login")}
          </Link>
        </p>
      </form>

      <Dialog open={termsOpen} onOpenChange={setTermsOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{t("auth.termsModalTitle")}</DialogTitle>
            <DialogDescription>{t("auth.termsModalHint")}</DialogDescription>
          </DialogHeader>

          <div
            className="max-h-[55dvh] space-y-4 overflow-y-auto pr-1"
            onScroll={(e) => {
              const el = e.currentTarget;
              if (el.scrollTop + el.clientHeight >= el.scrollHeight - 8) {
                setTermsScrolled(true);
              }
            }}
          >
            {TERMS_SECTIONS.map((section) => (
              <section key={section.title}>
                <h3 className="mb-1 font-semibold text-on-surface">{section.title}</h3>
                <p className="text-sm leading-relaxed text-on-surface-variant">{section.body}</p>
              </section>
            ))}
          </div>

          <DialogFooter>
            <Button
              className="w-full"
              disabled={!termsScrolled}
              onClick={() => {
                setTermsAccepted(true);
                setTermsOpen(false);
              }}
            >
              {t("auth.termsAccept")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
