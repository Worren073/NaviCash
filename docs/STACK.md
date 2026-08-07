# NaviCash — Decisiones de Stack (Fase 2)

> Complementa a `docs/PLAN.md`. Estado: **Fase 2 completada; implementado en Fase 3 (v0.6).**

---

## 1. Stack definitivo

| Capa | Tecnología | Versión objetivo | Justificación |
|---|---|---|---|
| Backend | **Django** | 5.2 LTS (soporte largo) | Lógica de negocio financiera con estado y concurrencia; testing maduro; sin lock-in |
| API | **Django REST Framework** | 3.16 | API REST con autenticación, serializers y permisos |
| BD | **PostgreSQL** | 17 | `NUMERIC`/enteros exactos, concurrencia MVCC, fechas/zonas horarias, futuro `pgvector` para IA |
| Frontend | **React + TypeScript** | React 19, TS 5.7 | Compartido con la futura migración a React Native |
| Build | **Vite** | 6.x | Arranque rápido, HMR, y base para el plugin PWA |
| UI | **Tailwind CSS v4 + shadcn/ui** | v4 | Mobile-first, accesible, dark/light, rápido de diseñar |
| Estado | **TanStack Query v5** | v5 | Cache y sincronización de datos de la API |
| Formularios | **react-hook-form + zod** | v7 / v3 | Validación tipada compartida con el backend |
| i18n | **react-i18next** | actual | Español latino con estructura lista para más idiomas |
| Animación/iconos | **motion + Its Hover** | motion 12 | Iconos animados open-source (Apache-2.0) integrados por copy-paste |
| PWA | **vite-plugin-pwa** | actual | Manifest + service worker, instalable, offline parcial |
| Dev | **Docker Compose** | — | Todo el stack local contenerizado; sin dependencias en la máquina |
| Deploy (Fase 5) | **Vercel** (frontend) + **Render** (backend + Postgres) | — | Vercel para PWA/estática; Render para Django + Postgres (riesgo R5) |

---

## 2. Backend — módulos y arquitectura

**Proyecto Django con apps modulares** (cada app = dominio de negocio):

```
services/api/
├── config/              # settings, urls, wsgi/asgi
├── apps/
│   ├── accounts/        # usuarios, auth (JWT + email + Turnstile), onboarding
│   ├── wallets/         # billeteras y saldos (auto-actualización + ajuste + transferencias)
│   ├── transactions/    # cobros/pagos/transferencias, estados, categorías, contactos
│   ├── savings/         # metas de ahorro, contribuciones y cuentas afiliadas
│   ├── subscriptions/   # mensualidades y renovación con gasto registrado
│   ├── shortcuts/       # atajos del home
│   ├── notifications/   # notificaciones in-app generadas al consultar (deduplicadas)
│   ├── overview/        # resumen de home (dashboard)
│   ├── rates/           # integración DolarApi, caché e histórico de tasas
│   └── core/            # utilidades compartidas, middleware, paginación
└── manage.py, pyproject.toml, Dockerfile
```

**Librerías clave**
- `djangorestframework` + `djangorestframework-simplejwt` — JWT access (corto) + refresh en cookie `httpOnly`.
- Email: `resend` (prod, plan gratis) / backend consola en dev. Verificación por token con expiración (tabla `email_verifications`).
- Tareas programadas: `django-apscheduler` en dev; en Render, **Cron Jobs** (un endpoint protegido por token) para: refrescar tasas y recalcular estados `retrasado`. El estado retrasado se calcula también al consultar (por zona horaria del usuario), el cron solo asegura consistencia.
- DB: `psycopg` (psycopg3). Migraciones con Django ORM.
- Config: `django-environ` con `.env`; secretos jamás en el repo.
- Tests: `pytest` + `pytest-django` + `factory-boy`. Lint/formato: `ruff`.

**Reglas de dinero (críticas, del plan R1/R2)**
- Montos en enteros de la menor unidad (`NUMERIC(20,2)` o tipo integer-minor). Nunca flotantes.
- Cada transacción congela `monto_usd` + `tasa_usd` + `fuente_tasa` al momento de registrar (nunca se recalcula el pasado).
- Actualización de saldo de billetera dentro de una **transacción de BD** (atómico): al marcar pagado, el cobro suma / el pago resta; editar/eliminar revierte.

**Integración DolarApi** (ADR-03)
- Servicio desacoplado (interfaz `RateProvider` + proveedor `DolarApiProvider`), para poder cambiar de fuente sin tocar consumo.
- Caché en tabla `exchange_rates` con TTL 1 h; fallback a última tasa con marca `desactualizada`. Tasa oficial (BCV) siempre.

---

## 3. Frontend — estructura

```
apps/web/
├── src/
│   ├── app/            # rutas (react-router), layout mobile, proveedores, guard de sesión
│   ├── features/       # por dominio: auth, dashboard, transactions, savings, wallets, profile
│   ├── components/
│   │   ├── ui/         # shadcn/ui + Skeleton (shimmer+blur), BlurLoading, Splash
│   │   └── icons/      # iconos animados Its Hover (motion/react) + tipos compartidos
│   ├── lib/            # cliente API tipado, formatos (monedas/fechas es-VE), tipos del contrato
│   ├── i18n/           # recursos de traducción (es) — react-i18next
│   └── hooks/          # query keys y hooks de datos (overview, wallets)
├── public/             # manifest, iconos PWA
└── vite.config.ts      # react plugin + vite-plugin-pwa + proxy /api
```

- **Cliente API tipado** (en `src/lib/api.ts`): consume REST de Django, inyecta token access, refresca con cookie httpOnly automáticamente, mapea errores a mensajes (`ApiErrorClass` con fieldErrors).
- **Estado de datos:** TanStack Query (cache, invalidation). Sesión ligera en memoria (access JWT); refresh en cookie httpOnly; nada sensible en localStorage.
- **Diseño mobile-first:** top bar + bottom nav flotante con FAB "nueva operación"; tokens "Liquid Glass" (teal `#006a61`, glass panels, Geist).
- **Micro-interacciones:** skeleton con shimmer+blur mientras cargan datos, transición fade/slide entre rutas, splash de arranque con el logo.
- **i18n:** español latino como única lengua activa; `resources = { es: { translation } }` listo para añadir idiomas.
- **A11y/UX finanzas:** confirmaciones para acciones destructivas, montos con formato `es-VE` ($ 1.234,56 / Bs 1.234,56), fechas adaptadas a la zona del usuario.

---

## 4. Monorepo y Docker Compose (desarrollo)

```
Aplicacion de finanzas/            (root = repo `navi`)
├── apps/web/                      # React 19 + Vite + TS (PWA)
├── services/api/                  # Django 5.2 + DRF
├── infra/
│   └── docker-compose.yml         # postgres + api + web (dev)
├── docs/
│   ├── PLAN.md
│   └── STACK.md
└── README.md, .gitignore, .env.example
```

> `packages/domain` (TS puro portable a RN) y `packages/api-client` están
> planificados para el futuro; hoy el cliente HTTP vive en `apps/web/src/lib/api.ts`.

Servicios en `docker-compose.yml` (implementados):
1. `db` — postgres:17 (volumen persistente, healthcheck).
2. `api` — Django; arranca migraciones + `refresh_rates` + `runserver` en `:8000`; depende de `db` sano; código montado en vivo.
3. `web` — Vite; dev server con proxy `/api → api:8000`; `npm install` automático al arrancar; código montado en vivo.

Reglas: sin instalaciones locales (todo dentro de contenedores); `.env.example` con variables; secretos solo en `.env`.

---

## 5. Despliegue (producción) — Fase 5

| Componente | Proveedor | Detalle |
|---|---|---|
| Frontend/PWA | **Vercel** | Build de `apps/web`, dominio propio, CDN |
| API REST | **Render** | Web service Django (gunicorn), Hobby $0 o Starter $7 |
| BD | **Render Postgres** | Desde $0 (30 días) / $6 básica; datos cifrados |
| Tareas programadas | **Render Cron Jobs** | Endpoint protegido: refrescar tasas + retrasos |
| Emails | **Resend** | Verificación/recuperación; plan gratis |
| DNS/dominio | — | Pendiente verificar `navicash.*` (ADR-07) |

Estrategia de entornos: `dev` (local Docker), `staging` (preview de Render/Vercel), `prod`.

---

## 6. Riesgos re-evaluados tras la decisión de stack
- **R5 resuelto:** backend en Render (no Vercel), frontend en Vercel. Vercel solo entrega estática/PWA.
- **R3 mitigado por diseño:** servicio de tasas desacoplado (`RateProvider`) + caché + fallback.
- **R6 confirmado:** `packages/domain` (TS puro) se crea en Fase 3 con el modelo de dominio para reusar en React Native en el futuro.
- **Nuevo:** versión de Python a fijar (3.12/3.13) y pinning de dependencias (uv/poetry/requirements) para builds reproducibles en Render.