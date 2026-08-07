<div align="center">

# NaviCash

### Finanzas personales en el bolsillo

Aplicación web **mobile-first · PWA** para llevar tus cobros, pagos, vencimientos, transferencias y metas de ahorro con el dólar como referencia. Escalable a React Native.

![v0.6](https://img.shields.io/badge/versi%C3%B3n-0.6.0-006a61?style=for-the-badge)
![Backend 124 tests](https://img.shields.io/badge/backend-124%20tests%20%C2%B7%20verde-4ade80?style=for-the-badge)
![Stack](https://img.shields.io/badge/React%2019-Django%205.2-PostgreSQL%2017-64748b?style=for-the-badge)
![Licencia](https://img.shields.io/badge/licencia-MIT-1e293b?style=for-the-badge)

</div>

## Características

- **Dashboard**: saldo consolidado en USD/VES, por cobrar, por pagar, retrasados, total ahorrado y tasa BCV del día.
- **Billeteras multi-moneda** (USD / VES): saldo original y equivalente en USD, ajuste manual de saldo, colores e iconos.
- **Transferencias entre cuentas**: mueve dinero entre billeteras (misma o distinta moneda) con tasa BCV o personalizada, preview del monto recibido e historial inmutable en el feed.
- **Cuentas de ahorro**: billeteras `tipo="saving"` separadas de las cuentas normales, con total de ahorro en el dashboard.
- **Metas de ahorro**: objetivo, moneda, fecha límite y **cuentas de ahorro afiliadas** (el avance suma el saldo real ahorrado).
- **Cobros y pagos**: registro rápido, estados (pendiente / pagado / retrasado / cancelado) y marcar con un tap.
- **Mensualidades**: seguimiento por tiempo (próxima / activa / finalizada) y renovación con registro del gasto sobre una cuenta.
- **Notificaciones in-app**: vencimientos próximos, operaciones vencidas y metas alcanzadas (deduplicadas, marcables como leídas).
- **Perfil y sesión**: registro con verificación de email + CAPTCHA Turnstile, JWT + refresh en cookie `httpOnly`, edición de perfil.
- **PWA instalable** con service worker y shell offline parcial.
- **i18n** en español latino, listo para más idiomas.
- **Micro-interacciones**: iconos animados (Its Hover) con animación al click, skeletons con blur y transiciones suaves entre vistas.

## Capturas

La UI está basada en las vistas de diseño "Liquid Glass" (`stitch_liquid_finance_ledger/`). Implementada en `apps/web` — capturas próximamente (puedes arrancar el proyecto para ver la app en vivo).

## Stack

| Capa | Tecnología |
|---|---|
| Frontend | React 19 · TypeScript 5.7 · Vite 6 · Tailwind CSS v4 · shadcn/ui |
| Backend | Django 5.2 LTS · Django REST Framework 3.16 |
| Datos | PostgreSQL 17 · ORM Django (montos `NUMERIC`, nunca flotantes) |
| Auth | JWT access + refresh en cookie `httpOnly`, verificación de email, Turnstile |
| PWA | `vite-plugin-pwa` (manifest + service worker) |
| i18n | react-i18next (es) |
| Infra | Docker Compose (dev) — sin instalar nada en la máquina |
| Deploy (plan) | Vercel (frontend) · Render (backend + Postgres) |

## Empezar (dev)

**Único requisito:** Docker + Docker Compose v2.

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up --build
```

| Servicio | URL |
|---|---|
| Frontend (SPA) | http://localhost:5173 |
| API (Swagger) | http://localhost:8000/api/schema/swagger-ui/ |
| PostgreSQL | localhost:5432 (interna al compose) |

El contenedor `web` ejecuta `npm install && npm run dev` al arrancar, así que
los cambios de `package.json` se instalan solos al recrear/restart el
contenedor.

## Estructura del repo

```
├── apps/web/            # Frontend: React + TS + Vite + Tailwind v4 + shadcn/ui (PWA)
│   └── src/
│       ├── app/         # rutas, layout, guard de sesión, proveedores
│       ├── features/    # auth, dashboard, transactions, savings, wallets, subscriptions, profile
│       ├── components/  # ui/ (shadcn + skeleton/lazos) e icons/ (Its Hover)
│       ├── lib/         # cliente API tipado, formatos es-VE, tipos del contrato
│       ├── i18n/        # traducciones (es)
│       └── hooks/       # query keys + hooks de datos
├── services/api/        # Backend: Django 5.2 + DRF
│   └── apps/            # accounts, wallets, transactions, savings, subscriptions, shortcuts, overview, notifications, rates, core
├── infra/               # docker-compose.yml (dev: db + api + web)
├── docs/                # PLAN.md (producto) · STACK.md (decisiones) · AUDIT.md (seguridad) · AI-ASSISTANT.md (plan IA)
└── stitch_liquid_finance_ledger/  # vistas de diseño de referencia
```

> `packages/domain` y `packages/api-client` (TypeScript puro portable a React Native)
> están planificados; hoy el cliente HTTP vive en `apps/web/src/lib/api.ts`.

## Comandos habituales

```bash
# Tests del backend (124 en verde)
docker compose -f infra/docker-compose.yml exec api python -m pytest

# Migraciones / superusuario
docker compose -f infra/docker-compose.yml exec api python manage.py migrate
docker compose -f infra/docker-compose.yml exec api python manage.py createsuperuser

# Tasa del dólar y retrasados
docker compose -f infra/docker-compose.yml exec api python manage.py refresh_rates
docker compose -f infra/docker-compose.yml exec api python manage.py recalc_overdue

# Frontend: typecheck + build de producción
docker compose -f infra/docker-compose.yml exec web npx tsc -b --noEmit
docker compose -f infra/docker-compose.yml exec web npm run build
```

## Documentación

- [Plan de producto](docs/PLAN.md) — visión, ADRs, requisitos, riesgos y roadmap.
- [Decisiones de stack](docs/STACK.md) — arquitectura backend/frontend, despliegue.
- [Auditoría de seguridad](docs/AUDIT.md) — hallazgos, riesgos y plan de endurecimiento (v0.6).
- [Asistente IA](docs/AI-ASSISTANT.md) — plan de implementación del asistente conversacional (v0.7).

## Roadmap

| Versión | Contenido |
|---|---|
| **v0.6 (actual)** | Transferencias entre cuentas, billeteras/ahorro, mensualidades, notificaciones in-app, auditoría de seguridad. |
| v0.6.1 / hardening | Fixes de la auditoría: throttling, cookies seguras, blacklist del refresh, secretos sin default. |
| v0.7 | Asistente IA conversacional (análisis, recomendaciones, "¿puedo permitirme X?"). |
| v1 | Testeo visual/E2E, despliegue en producción (Vercel + Render), verificación de marca `navicash.*`. |
| v2 | Tarjetas y cortes, importar CSV, informe mensual de ingresos/gastos. |
| v3 | Notificaciones push nativas al portar a móvil, integración bancaria (según región). |

## Contribuir

Repo abierto a PRs e issues. Para aportar: fork → rama → cambios → PR, explicando qué resuelve y verificando que pasen los tests (`api`/`web`). Revisa [PLAN.md](docs/PLAN.md), [STACK.md](docs/STACK.md) y [AUDIT.md](docs/AUDIT.md) antes.

## Licencia

MIT — ver archivo `LICENSE` (pendiente de añadir). Iconos animados: Its Hover (Apache-2.0).
</div>
