# Informe de auditoría pre-producción — NaviCash

**Fecha:** agosto 2026 · **Alcance:** auditoría solo-lectura (sin cambios de código) por 4 agentes senior: backend (Django/DRF), frontend (React 19/TS/Vite), base de datos (PostgreSQL 17) y seguridad (AppSec). **Commit auditado:** `06581b7` (186 tests en verde).

**Estado general:** la arquitectura es sólida (owning correcto por usuario, Decimal+HALF_UP en dinero, conversión congelada, asistente con fallback determinista y countermeasures anti-inyección, JWT access en memoria + refresh httpOnly, sin XSS directo ni secretos commiteados). **No está lista para producción mañana:** hay 4 riesgos críticos operacionales y una configuración fail-open que deben cerrarse antes del lanzamiento.

---

## 1. Hallazgos CRÍTICOS

### C1 — Carrera de lectura-escritura en saldos (doble gasto / pérdida de actualización)
- **Dónde:** `services/api/apps/wallets/services.py:19-47` (usado por transactions, transferencias, suscripciones, wallets)
- **Qué pasa:** `adjust_balance` lee `saldo` en memoria y escribe sin bloquear la fila. Dos requests concurrentes (doble clic, retry, pago + transferencia simultáneos) validan ambos contra el mismo saldo y el último write gana: sobregasto o saldo incorrecto irreparable.
- **Acción:** `wallet = Wallet.objects.select_for_update().get(pk=...)` dentro de `transaction.atomic()` + revalidar `new_balance >= 0`. Refuerzo en BD: `CheckConstraint(saldo >= 0)`.

### C2 — Caché no configurada en producción (rate limits y confirmaciones volátiles)
- **Dónde:** `config/settings.py` (sin `CACHES`; solo existe en `test_settings.py`)
- **Qué pasa:** `LocMemCache` por proceso: con gunicorn multi-worker el throttle del asistente (30/h) es por worker y las **transferencias pendientes de confirmación** ("sí") se guardan en un worker arbitrario → pérdida de propuesta o doble ejecución.
- **Acción:** `CACHES` con `django-redis` → `RedisCache`, y confirmación idempotente con `cache.add()`.

### C3 — La rotación del refresh token no revoca el token usado
- **Dónde:** `services/api/apps/accounts/views.py:117-135` + `settings.py:180-181`
- **Qué pasa:** `ROTATE_REFRESH_TOKENS`/`BLACKLIST_AFTER_ROTATION` activos, pero el `RefreshView` manual emite el nuevo token **sin `refresh.blacklist()`** ni `check_blacklist()` el usado. Un refresh robado se reutiliza 30 días y sobrevive al logout.
- **Acción:** usar `TokenRefreshSerializer` estándar de SimpleJWT y/o `blacklist()` explícito; revocar la familia al logout (`OutstandingToken` por user); considerar reuse-detection.

### C4 — Borrado físico de datos financieros sin soft-delete ni auditoría
- **Dónde:** `apps/transactions/views.py:89-99` (`perform_destroy`), `apps/core/models.py:49-54` (`CASCADE` en User), `apps/savings/models.py:125-130`
- **Qué pasa:** un DELETE borra historial financiero irrecuperable; borrar un usuario cascada sobre todo su historial. Sin pista de auditoría de quién/cuándo tocó saldos.
- **Acción:** soft-delete (`is_deleted` + manager) para Transaction/Wallet/Contributions; `PROTECT` en cascadas de meta; tabla `BalanceAuditLog(wallet, delta, reason, user, created_at)` escrita en la misma transacción de `adjust_balance`.

---

## 2. Hallazgos ALTOS

### A1 — Sin throttling ni CAPTCHA obligatorio en auth (fuerza bruta directa)
- `accounts/views.py:59-105,160-172` (login/register/verify sin throttle; `AllowAny`), `captcha.py:14-30` (`CAPTCHA_DEV_BYPASS=True` por defecto → fail-open total) y frontend `register-page.tsx:21,100` (widget solo si `VITE_CAPTCHA_SITE_KEY` está seteada).
- **Acción:** `AnonRateThrottle`/scoped (`login 5/min`, `register 3/h`); en prod exigir `TURNSTILE_SECRET_KEY` (fail-closed con `DEBUG=False`); `VITE_CAPTCHA_SITE_KEY` obligatoria en build + `.env.example`.

### A2 — Configuración fail-open: DEBUG/secr etos con valores conocidos
- `config/settings.py:22-23,29,46-49`: `DEBUG=True` por defecto, `DJANGO_SECRET_KEY="dev-secret-key…"`, `POSTGRES_PASSWORD` de desarrollo.
- **Acción:** fail-fast: si `DEBUG=False` y la clave es la conocida/vacía → `ImproperlyConfigured`; `DEBUG` sin default; test que falle si `DEBUG and not settings.TEST`.

### A3 — Sin HTTPS/HSTS/hardening de cookies detrás de proxy
- `config/settings.py:90-100`: sin `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `SECURE_PROXY_SSL_HEADER`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`.
- **Acción:** bloque `SECURE_*` condicionado a `not DEBUG`, incluyendo `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`.

### A4 — El contenedor web sirve el dev server de Vite como "producción"
- `apps/web/Dockerfile:18-19` (`npm run dev`), proxy `/api → localhost:8000` roto dentro del contenedor, sin headers, sin build.
- **Acción:** multi-stage build → `dist/` servido por nginx (SPA `try_files`, headers CSP/nosniff/no-referrer); URL de API explícita por env; exponer 80/443.

### A5 — LLM y DolarApi síncronos dentro del request (agotamiento de workers, thundering herd)
- `assistant/providers.py:121` (timeout 60 s), `rates/providers.py:96`, `rates/service.py:96-99` (refresco sin single-flight).
- **Acción:** LLM a cola o `httpx timeout ≤ 25 s` (el fallback ya cubre); tasas con lock de refresco (`cache.add`/advisory lock) y caché activa en Redis.

### A6 — Fallback de tasa "1.0" corrompe conversiones USD congeladas para siempre
- `rates/service.py:109-127` devuelve `Decimal("1")` cuando DolarApi falla; la conversión se congela en BD por diseño.
- **Acción:** no registrar con tasa 1: `BusinessRuleError`/503 o persistir `fuente_tasa="fallback"` excluida de reportes.

### A7 — Refresh sin verificar blacklist/is_active (logout inefectivo, cuentas desactivadas siguen renovando)
- `accounts/views.py:117-135`, `JWTAuthentication.get_user` sin chequear `is_active`.
- **Acción:** `refresh.check_blacklist()` + `user.is_active` en el flujo de refresh (ver C3).

### A8 — N+1 en metas de ahorro, notificaciones y transferencias listadas
- `savings/serializers.py:45-59` (3 queries por meta: `count()`, `aggregate`, `linked_accounts.all()`), `transactions/views.py:41-45` (falta `dest_wallet` en `select_related`), `notifications/services.py:51-83` (write-on-GET por fila).
- **Acción:** `prefetch_related("contributions","linked_accounts")` + `len()`/sum en Python; añadir `dest_wallet`; dedupe con índice único en notificaciones.

### A9 — Índices faltantes para los patrones de consulta reales
- Notificaciones (`user, created_at`; `user, read`), chat (`user, session_id`), pagadas recientes (`user, estado, -fecha_pagado`), aportes (`goal, -created_at`).
- **Acción:** `CREATE INDEX CONCURRENTLY …` (o `models.Index` + migración) antes de migrar datos grandes.

### A10 — Integridad solo a nivel de aplicación (sin CheckConstraints)
- Montos/ saldos/ tasas negativas y estados inválidos aceptados por el motor.
- **Acción:** `CheckConstraint`: `monto > 0`, `saldo >= 0`, `tasa_usd > 0`, `estado/tipo IN (...)`, `fecha_vencimiento >= fecha`; en tablas con datos: `NOT VALID` + `VALIDATE`.

### A11 — Sesión expirada no cierra la sesión (401 sin interceptor global) y no hay Error Boundaries
- `apps/web/src/lib/api.ts:110-123`, `router.tsx:22-49,51`, `main.tsx:9`: el usuario queda atascado en sesión muerta; un error de render → pantalla blanca.
- **Acción:** interceptor 401 global → logout + navegación; `ErrorBoundary` raíz + `queryCache.onError`.

### A12 — Fetch sin `AbortSignal` ni timeout en el front
- `apps/web/src/lib/api.ts:87-124`: peticiones que cuelgan indefinidamente (red muerta → skeletons infinitos).
- **Acción:** `queryFn` con `signal`, `AbortSignal.timeout(10_000)`, abort del chat de voz al cerrar.

---

## 3. Hallazgos MEDIOS

| # | Hallazgo | Dónde | Acción |
|---|----------|-------|--------|
| M1 | `.env` local con API key real del LLM | raíz (ignorada, no commiteada) | **Rotar la clave ya**; inyectarla solo por env var/secret manager |
| M2 | Sin `LOGGING` configurado (500s y fallos LLM sin rastro) | `config/settings.py` | LOGGING estructurado a stdout (+ Sentry opcional); sanear `logger.exception` (no loguear payloads) |
| M3 | `/admin/` expuesto sin 2FA ni restricción | `config/urls.py:11` | allowlist por red/IP o desactivar en prod; tokens de verificación de email guardarlos hasheados |
| M4 | Sin paginación en historial del chat ni aportes | `assistant/views.py:62-78`, `savings/views.py:61-75` | `[:50]` o `DefaultPagination` + throttle |
| M5 | Retención ilimitada: chat, notificaciones leídas, blacklist, ExchangeRate | modelos de assistant/notifications/rates | job de purga (chat 180d, notif 90d, blacklist 30d, tasas 180d) + refresco `--if-stale` |
| M6 | Agregaciones del dashboard en Python (`aggregate_by_category`, `fin_month`, `build_summary` 5+ queries) | `overview/services.py:27-152`, `assistant/context.py:45-65` | `Sum/values().annotate()` en SQL + caché Redis 30-60 s en resumen |
| M7 | Conexión PG sin pool, sin SSL, `CONN_MAX_AGE=0`, puerto 5432 publicado | `settings.py:124-133`, `docker-compose.yml` | `CONN_MAX_AGE=60` + `CONN_HEALTH_CHECKS` + `sslmode=require`; contenedor API con gunicorn; no publicar 5432 |
| M8 | Turnstile deshabilitado por defecto en front (anti-bot opcional) | `register-page.tsx:21,100` | fail en build si falta `VITE_CAPTCHA_SITE_KEY`; CSP para `challenges.cloudflare.com` |
| M9 | i18n: solo `es` y clave `assistant.typing` visible literal | `i18n/index.ts`, `assistant-chat.tsx:57` | añadir `en` (o retirar promesa) + clave `typing` ya |
| M10 | Sin code splitting: bundle único (motion + voz + todo) | `app/router.tsx:4-14` | `React.lazy` por ruta + `manualChunks`; voz fuera del chunk inicial |
| M11 | Accesibilidad: zoom bloqueado (`maximum-scale=1`), contraste `#4ade80`≈1.9:1, chat flotante sin `role="dialog"`/focus trap, `Segmented` sin `aria-pressed` | `index.html:7`, `index.css:55-59`, `assistant-chat.tsx:37-126` | quitar límite de zoom; tokens de texto vs fondo; dialog + focus trap; `prefers-reduced-motion` |
| M12 | `npm run lint` roto (eslint no instalado); CI sin gates | `apps/web/package.json:10` | eslint + typescript-eslint + exhaustive-deps en CI |
| M13 | No existe recuperación/cambio de contraseña | `accounts/emails.py:42-58` (código muerto) | `forgot/reset-password` con token hash + `change-password` autenticado |
| M14 | Gunicorn ausente de requirements y sin `STATIC_ROOT`/whitenoise | `requirements.txt`, `settings.py:246` | fijar versiones exactas + `gunicorn` + whitenoise/collectstatic |

---

## 4. Deuda técnica (BAJA, planificable)

- **B1** Precisión decimal: tasa `decimal_places=4` puede truncar tasas BCV futuras → subir a 6; validar rango de `monto * tasa` antes de insertar (`max_digits=20`).
- **B2** Migración `0002_user_profile_terms` con `save()` fila a fila → `bulk_update` con batch (importante solo con decenas de miles de usuarios).
- **B3** Dependencias Python con rangos `>=,<` (builds no reproducibles) → `requirements.lock` + `pip-audit`/Dependabot; dependencias muertas en front: `react-hook-form`, `zod`, `@hookform/resolvers` sin uso → eliminar.
- **B4** `ExchangeRate` duplicada por carreras de refresco → índice único `(currency, rate_date) WHERE source='oficial'` + single-flight.
- **B5** Enumeración de cuentas en registro ("Ya existe una cuenta con este correo") → respuesta genérica.
- **B6** Particionado/archivado por fecha para transacciones (>10M filas, futuro).

---

## 5. Plan de acción recomendado (antes de producción)

**Fase 0 — Bloqueantes (días 1-3)**
1. C1 `select_for_update` + C2 Redis `CACHES` + idempotencia de confirmación.
2. C3/A7 refresh con blacklist real y logout que revoca la familia.
3. C4 soft-delete + tabla de auditoría de saldos.
4. A2 fail-fast de secrets/DEBUG + A3 hardening HTTPS/cookies + A7.

**Fase 1 — Seguridad y auth (días 3-5)**
5. A1 throttling login/register/verify + Turnstile obligatorio en prod (back y front) + M1 **rotación de la API key** + M13 recuperación de contraseña + M3 admin restringido.

**Fase 2 — Operación (días 5-8)**
6. A4 Dockerfile web a producción (build+nginx) + A5 LLM/tasas asíncronos o con timeout + A6 nunca tasa=1 + M7 gunicorn/pool/SSL + M2 logging + M14 requirements fijos.

**Fase 3 — Datos y rendimiento (días 8-12)**
7. A8 prefetch en metas/notifs/transferencias + A9 índices CONCURRENTLY + A10 CheckConstraints + M5 retención/purga + M6 agregaciones SQL + caché de resumen + M4 paginación.

**Fase 4 — Frontend y calidad (días 12-15)**
8. A11 interceptor 401 + ErrorBoundary + A12 abort/timeout + M8-M12 (Turnstile build, i18n, code splitting, a11y, lint en CI) + B3 (dependencias muertas) .

**Después del lanzamiento:** m onitoreo (Sentry, métricas), `pip-audit`/Dependabot continuo, B1/B2/B4/B6 en backlog técnico.

---

## 6. Estado de implementación — Iteración 1 (seguridad, auth e integridad) ✅

**Fecha:** agosto 2026 · **Verificación global:** suite backend **222 passed + 2 skipped** (concurrencia solo en Postgres real), typecheck frontend 0 errores, `manage.py check` 0 issues, `makemigrations --check` sin pendientes, migraciones aplicadas en dev.

| Hallazgo | Qué se implementó | Ubicación |
|----------|-------------------|-----------|
| **A2** fail-fast | `DEBUG` sin default (ausente → prod), `DJANGO_SECRET_KEY`/`POSTGRES_PASSWORD` sin default dev + `ImproperlyConfigured` en prod; `test_settings.py` fuerza `DEBUG=1` | `config/settings.py:22-31,76-98`, `config/test_settings.py:10-14`, `infra/docker-compose.yml:43-55` |
| **A3** hardening HTTPS | `SECURE_PROXY_SSL_HEADER`, `SECURE_SSL_REDIRECT`, HSTS 1 año, `SESSION/CSRF_COOKIE_SECURE` solo prod | `config/settings.py:236-248` |
| **A1** throttling+Turnstile | Rates globales (`login 5/min`, `register 3/h`, `email_verify 10/h`, `assistant 30/h`); scopes en login/register/verify/refresh; captcha fail-closed (`captcha.py:16-47`); build frontend exige `VITE_CAPTCHA_SITE_KEY` (`vite.config.ts:12-13`) | `config/settings.py:178-192`, `apps/accounts/views.py:89,119,147,212`, `apps/web/vite.config.ts` |
| **C3/A7** refresh+logout | `check_blacklist()` + `is_active` + reuse-detection; `blacklist()` al rotar; logout revoca la familia de OutstandingToken | `apps/accounts/views.py:67-74,137-207` |
| **C1** integridad de saldos | `select_for_update` + revalidación `< 0` + `save(update_fields)` + sincronización de la instancia; `CheckConstraint saldo>=0`; test de concurrencia real (threads, Postgres) | `apps/wallets/services.py:19-58`, `apps/wallets/models.py:82-88`, `migrations/0004`, `tests/test_wallets.py:90-154` |
| **M13** recuperación | `PasswordResetToken` (sha256, 30 min, one-time) + `POST /auth/forgot-password|reset-password|change-password` + UI forgot/reset + link en login + clave i18n `assistant.typing` | `apps/accounts/models.py:197-253`, `views.py:221-279`, `urls.py:40-42`, web: `forgot-password-page.tsx`, `reset-password-page.tsx`, `api.ts:138-146` |
| **B5** enumeración | Registro duplicado responde 201 genérico «Revisa tu correo…» (sin crear cuenta) | `apps/accounts/serializers.py:116-139`, `views.py:95-99` |
| **B5/M13** tokens | `EmailVerification.token` y reset tokens almacenados como hash sha256 | `apps/accounts/models.py:153-187` |
| **M1** API key | La clave real del LLM sigue en `.env` local (no commiteada): **pendiente de rotación por el usuario** en el proveedor | — |

**Pendientes para la Iteración 2 (operativo):** C2 caché Redis (confirmaciones del asistente + rate limits compartidos), C4 soft-delete + auditoría de saldos, A4 Dockerfile web a `nginx/build`, A5 LLM/tasas fuera del request, A6 nunca tasa=1, A8-A10 N+1/índices/CheckConstraints restantes, M2 logging, M3 admin restringido, M4-M7, M9-M12 frontend, B1-B6.