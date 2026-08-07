# NaviCash — Auditoría de seguridad y mejora (v0.6)

> Fecha: agosto 2026 · Alcance: `apps/web` (frontend) y `services/api` (backend).
> Estado: **auditoría completada** — los fixes se aplican en la iteración de hardening (v0.6.1).

---

## 1. Resumen ejecutivo

La base de código está **bien estructurada y saneada en lo esencial**:

- ✅ JWT access en memoria + refresh en cookie `httpOnly` (`Lax`, `secure` en prod), sin nada sensible en `localStorage`.
- ✅ Owner-scoping en todos los viewsets (`IsOwner` + filtro por `request.user`) — sin IDOR detectado.
- ✅ Serializadores con querysets acotadas al usuario, dobles comprobaciones de propiedad.
- ✅ Argon2 + validadores de contraseña; `max_page_size=100`; errores sin stack traces al cliente.
- ✅ Sin `dangerouslySetInnerHTML`, sin `console.log` con datos sensibles, sin secretos hardcodeados; `.env` fuera de git.
- ✅ PWA sin `runtimeCaching` de `/api` (no se cachean datos privados).

Los hallazgos relevantes están concentrados en **hardening de producción** y **rate limiting**, más tres bugs concretos (rotación de refresh, guard de sesión, lint roto).

---

## 2. Hallazgos por riesgo

### 🔴 Alto

| # | Hallazgo | Ubicación | Fix sugerido |
|---|---|---|---|
| A1 | **Sin `SECURE_SSL_REDIRECT`, HSTS, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_CONTENT_TYPE_NOSNIFF`, `SECURE_PROXY_SSL_HEADER`** | `config/settings.py` | Bloque `SECURE_*` condicionado a `not DEBUG` (incluye `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` para Render) |
| A2 | **`DEBUG=True` y `DJANGO_SECRET_KEY` con default conocido** si falta env en producción (`dev-secret-key-cambiar-en-produccion` permite forjar JWTs) | `config/settings.py:22-23` | Leer de env sin default y lanzar `ImproperlyConfigured` si faltan; `DEBUG=False` forzado en prod |
| A3 | **La rotación del refresh no añade el token usado al blacklist** (`RefreshView` manual; `ROTATE_REFRESH_TOKENS` queda muerto). Un refresh robado es reutilizable 30 días | `apps/accounts/views.py:108-135` | Llamar `refresh.blacklist()` al rotar + revocación de familia (`OutstandingToken` por `user_id`) |
| A4 | **Sin rate limiting en ningún endpoint**: fuerza bruta a login, spam de registro (CAPTCHA off por defecto: `TURNSTILE_SECRET_KEY=""` + `CAPTCHA_DEV_BYPASS=True`) | `config/settings.py:46-49,156-169` | `DEFAULT_THROTTLE_CLASSES`/`RATES` (login 5/min, register 3/h, anon 100/min); fijar `TURNSTILE_SECRET_KEY` en prod y `CAPTCHA_DEV_BYPASS=False` |

### 🟠 Medio

| # | Hallazgo | Ubicación | Fix sugerido |
|---|---|---|---|
| M1 | `/admin` expuesto sin protección extra (sin 2FA, sin `SESSION_COOKIE_SECURE`, sin rate limit) | `config/urls.py:11` | Restringir por red/proxy, `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE`, o desactivar en prod |
| M2 | **ESLint inexistente**: `npm run lint` falla (sin paquete ni config) | `apps/web/package.json:10` | Añadir `eslint` + config (`eslint.config.js`) como gate de calidad |
| M3 | **Sin CSP ni security headers** en `index.html`; Turnstile y Google Fonts sin SRI/nonce | `apps/web/index.html` | `Content-Security-Policy`, `X-Content-Type-Options`, `frame-ancestors`; `integrity` en `<script>` |
| M4 | **Guard `RequireAuth` solo valida al montar** (`[]`); una sesión expirada no redirige al navegar | `apps/web/src/app/router.tsx:26-42` | Re-validar por navegación (depender de `location.pathname`) o redirigir en 401 global |
| M5 | **Colores de servidor inyectados en `style` sin validar formato hex** (`wallet.color`, `sub.color`) | `wallets-page`, `subscriptions-page`, `savings-page`, `card-glow.tsx` | Validar `^#[0-9a-fA-F]{6}$` en el backend y/o en el cliente antes del `style` |
| M6 | **`i18next` con `escapeValue: false`** (seguro hoy por render JSX, riesgo si se usa HTML en el futuro) | `apps/web/src/i18n/index.ts` | Documentar el fence y prohibir `dangerouslySetInnerHTML`; usar `Trans` + escape si hace falta |
| M7 | Contenedor `web` ejecuta **`npm run dev`** (no apto para producción) | `infra/docker-compose.yml` + `Dockerfile` | Para prod: `npm run build` + servir `dist/` con nginx/static y headers |

### 🟡 Bajo / mejora

| # | Hallazgo | Ubicación | Sugerencia |
|---|---|---|---|
| L1 | `aggregate_by_category` carga todas las transacciones del usuario en memoria | `apps/overview/services.py:130-152` | Agregar con `Sum`/`GroupBy` en SQL |
| L2 | Dependencias Python con rangos `>=,<` sin fijar parches | `services/api/requirements.txt` | `pip-compile`/lockfile + `pip-audit`/Dependabot en CI |
| L3 | `debug_token` en respuesta de registro (gateado por `DEBUG`, OK hoy) | `apps/accounts/views.py:75-77` | Mantener solo en dev (ya es así); añadir test que lo omita en prod |
| L4 | Sin handler JSON uniforme para 500 no-DRF | `apps/core/exceptions.py:43-44` | Handler que loguee contexto y devuelva JSON |
| L5 | `CurrentRateView` sin `permission_classes` explícito (usa default OK) | `apps/rates/views.py:12-30` | Explicitarlo para claridad |

---

## 3. Fortalezas confirmadas

- Refresh token en cookie `httpOnly` con `SameSite=Lax` y path restringido a `/api/auth/`.
- `BLACKLIST_AFTER_ROTATION` + blacklist funcional en logout; un refresh ya revocado falla con 401.
- Owner-scoping (`IsOwner` + `get_queryset`) en wallets, transactions, savings, subscriptions, shortcuts, notifications.
- `AllowAny` solo en register/login/refresh/verify-email.
- Paginación con tope (`max_page_size=100`); notificaciones limitadas a 30.
- Sin XSS directos (sin `innerHTML`/`dangerouslySetInnerHTML`), sin logs sensibles, sin localStorage.
- CORS con lista explícita + `CORS_ALLOW_CREDENTIALS=True` (correcto para cookie).
- Montos siempre `Decimal`/`NUMERIC`; conversiones congeladas por operación.

---

## 4. Plan de hardening (v0.6.1)

1. **A4 primero** — throttling DRF + Turnstile obligatorio en prod.
2. **A3** — `refresh.blacklist()` en `RefreshView` + revocación por familia.
3. **A1/A2** — bloque `SECURE_*` en settings condicionado a `not DEBUG`; `DJANGO_SECRET_KEY`/`DEBUG` sin default.
4. **M1** — restricción de `/admin` + cookies seguras.
5. **M2/M3** — ESLint configurado y CSP en `index.html`.
6. **M4** — guard de sesión reactivo a la navegación.
7. **M5** — validación de color hex (backend + cliente).
8. **L1–L5** — mejoras de rendimiento/reproducibilidad según disponibilidad.
