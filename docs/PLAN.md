# NaviCash — Plan de Proyecto

Aplicación web de finanzas personales, mobile-first, convertible a PWA y escalable a aplicaciones nativas.

> Nombre comercial: **NaviCash**. Nombre interno de código/repo: `navi`.

> Estado: **v0.6 — funcionalidad ampliada** (backend y frontend completos, pruebas en verde; roadmap IA en preparación)

---

## 1. Resumen del proyecto

| Campo | Valor |
|---|---|
| **Nombre** | NaviCash (código interno: `navi`) |
| **Tipo** | Web app mobile-first → PWA → nativas |
| **Función principal** | Llevar finanzas personales: cobros, pagos, pagos pendientes/retrasados, ahorro, atajos |
| **Moneda de referencia** | USD (con conversión multi-moneda vía DolarApi) |
| **Mercado inicial** | Venezuela, con arquitectura multi-moneda y multi-idioma para crecer a LatAm |
| **IA** | Roadmap **v0.7** (asesor financiero conversacional; plan en `AI-ASSISTANT.md`) |
| **Objetivo técnico** | Stack modular, APIs REST seguras, todo contenerizado en Docker Compose, despliegue en Vercel |

---

## 2. Visión

Llevar el control de las finanzas personales desde el bolsillo: anotar **cobros** y **pagos**, saber qué está **pendiente** o se **retrasó**, ahorrar hacia **metas**, y resolver todo con **atajos rápidos** — sin hojas de cálculo ni app bancaria. El dólar como referencia da contexto claro en una economía dolarizada, y un **asistente de IA** (a futuro) ayudará a interpretar y mejorar las finanzas.

### 2.1 Objetivos
- App completamente funcional y fácil de entender en su priming versión.
- Entrada rápida de datos (menos de 10 segundos por operación).
- Recordatorios proactivos de pagos pendientes/retrasados.
- Sistema de conversión multi-moneda con el dólar como referencia, robusto ante caídas de la API de tasas.

---

## 3. Fases del proyecto

| Fase | Nombre | Estado |
|---|---|---|
| 1 | Planificación | **Completada** |
| 2 | Selección de stack | **Completada** |
| 3 | Desarrollo (backend, APIs, BD, frontend) | **Completada (v0.6)** |
| 4 | Testeo (visualización, seguridad, funcionalidades) | **En curso** (backend 124 tests ✓; auditoría de seguridad documentada en `AUDIT.md`; pendiente E2E/visual completo) |
| 5 | Despliegue (producción, Vercel + host backend) | Pendiente |
| 6 | Mantenimiento y actualizaciones | Pendiente |

### Estado v0.6 en una línea
- **Backend (Django 5.2 + DRF + PostgreSQL):** apps accounts, wallets, transactions, savings, subscriptions, shortcuts, overview, notifications, rates y core; **124 tests en verde** (auth con JWT+refresh httpOnly y Turnstile, saldos y ajuste, estados, transferencias entre cuentas, metas con cuentas afiliadas, mensualidades y renovación, notificaciones, tasas BCV con caché/fallback).
- **Frontend (React 19 + Vite + Tailwind v4 + shadcn/ui):** mobile-first PWA con login/registro/verificación, dashboard con resumen/actividad/total ahorrado, billeteras normales y de ahorro con transferencia entre cuentas, nueva operación, operaciones con estados y vista de transferencia, mensualidades con renovación, metas de ahorro con cuentas afiliadas y perfil. i18n en español, iconos animados con animación al click, navbar translúcida, skeletons con blur y transiciones entre vistas.
- **Pendiente para v0.6.1/v1:** aplicar fixes de la auditoría de seguridad (`AUDIT.md`), cerrar testeo visual/E2E, desplegar en producción y verificar la marca `navicash.*`.

---

## 4. Decisiones tomadas (registro de decisiones)

### ADR-01 — Mercado inicial
- **Decisión:** Mercado inicial Venezuela, con diseÃ±o multi-moneda y multi-idioma desde el inicio.
- **Motivo:** mercado cercano, economía dolarizada (uso diario de Bs y USD).
- **Efecto:** formato de números/fechas latinoamericano, zona horaria Venezuela (UTC-4), monedas VES y USD activas desde el día 1.

### ADR-02 — Multi-moneda completo desde el inicio
- **Decisión:** soporte multi-moneda desde el MVP, con USD como moneda de referencia para reportes consistentes.
- **Motivo:** migrar a multi-moneda después es costoso e invita a reescribir el modelo de datos.
- **Efecto:** toda transacciÃ³n guarda su monto original (moneda + cantidad) y una conversión a USD con la tasa usada. Los montos monetarios NUNCA se guardan como coma flotante (ver Riesgo R1).

### ADR-03 — Conversión vía DolarApi
- **Decisión:** usar `https://ve.dolarapi.com` (API pública MIT) para tasas de dólar en Venezuela.
- **Endpoints verificados (ago 2026):**
  - `GET https://ve.dolarapi.com/v1/dolares` — lista de tasas (oficial, paralelo, etc.)
  - `GET https://ve.dolarapi.com/v1/dolares/oficial` — tasa dado el BCV (promedio)
  - `GET https://ve.dolarapi.com/v1/dolares/paralelo` — tasa paralela
  - Históricos disponibles: `/v1/dolares/historicos/...`
- **Formato respuesta** (oficial): `{ "moneda": "USD", "fuente": "oficial", "nombre": "Dólar", "compra": null, "venta": null, "promedio": 752.09, "fechaActualizacion": "..." }`
- **Efecto:** el backend consulta/guarda tasas en caché (nunca se depende de la API en cada lectura). **Política de selección de tasa: BCV oficial (promedio) SIEMPRE.** No hay selección de tasa por operación; paralelo/quedan solo como datos de referencia no aplicables al MVP.

### ADR-04 — Alcance MVP
- **En el MVP:** cobros y pagos con estados (pendiente / pagado / retrasado / cancelado), ahorro y metas, atajos, y home dashboard con resumen.
- **Fuera del MVP (roadmap):** manejo de tarjetas, asistente IA, integración bancaria automÃ¡tica, importación CSV, informes avanzados.

### ADR-05 — Registro de datos
- **Decisión:** solo registro manual en el MVP (sin integración bancaria ni CSV).
- **Motivo:** cero dependencias externas, sin riesgo de credenciales bancarias en la primera versión.
- **Nota:** importación CSV queda en el roadmap (v2) como vía rápida de entrada.

### ADR-06 — Autenticación
- **Decisión:** email + contraseña con verificación de email.
- **Efecto:** flujo completo de registro, login, logout, confirmación de email y recuperación de contraseña. Sin dependencia de OAuth en MVP.

### ADR-07 — Marca comercial
- **Decisión:** nombre comercial **NaviCash** (variante de "Navi", que estaba ocupado: `navi.com` = fintech india de préstamos; `navi.app` = app de viajes con IA ya activa).
- **Efecto:** pendiente verificar disponibilidad de `navicash.com`, `navicash.app`, tiendas (Google Play/Apple) y redes sociales antes de la fase de despliegue (ver R11).

### ADR-08 — Saldos de billetera
- **Decisión:** al marcar una operación como **pagada**, la billetera se actualiza automáticamente (cobro suma, pago resta), SIEMPRE con posibilidad de **ajuste manual** del saldo.
- **Efecto:** el saldo de billetera refleja la operativa diaria; el ajuste manual cubre errores de tipeo y saldos que no pasan por la app (p. ej. efectivo gastado sin registrar).

### ADR-09 — Recordatorios de vencimientos
- **Decisión:** regla **global** (avisar N días antes, configurable) + **sobrescritura opcional por operación** (`remind_me` / días de aviso propios).
- **Efecto:** los avisos de próximos vencimientos en home/dashboard usan la regla global por defecto; cada cobro/pago puede definir su propio aviso.

### ADR-10 — Idioma y moneda por usuario
- **Decisión:** UI en **español latino/neutro**, con estructura i18n preparada para añadir más idiomas. La moneda base de visualización la **elige el usuario al registrarse** (onboarding).
- **Efecto:** los usuarios nuevos pasan por un paso de onboarding donde fijan su moneda base; el resto de operaciones almacena siempre su moneda original (multi-moneda).

### ADR-11 — Transferencias entre cuentas (v0.6)
- **Decisión:** transferencia entre billeteras propias como un tercer tipo de operación (`tipo="transferencia"`). El monto se registra en la moneda de la cuenta **origen** y el destino se calcula: `USD → VES` multiplica por la tasa (venta) y `VES → USD` divide (compra). Misma moneda ⇒ tasa 1, sin conversión.
- **Tasa:** por operación, **BCV oficial** o **personalizada** (validada > 0). Las transferencias son **inmutables**: no se editan ni borran (se revierten con otra transferencia en sentido contrario).
- **Efecto:** feed/historial muestra "Cuenta A → Cuenta B" y el monto destino cuando hay cambio de moneda.

### ADR-12 — Billeteras de ahorro y cuentas afiliadas (v0.6)
- **Decisión:** una billetera puede ser `tipo="saving"` (cuenta de ahorro) y una meta de ahorro puede **afiliarse** a una o varias cuentas de ahorro (`linked_accounts`, solo `tipo="saving"`).
- **Efecto:** el avance de una meta suma aportes manuales + saldo de las cuentas afiliadas (convertido con la tasa oficial del día con las cuentas). En el dashboard, el **total ahorrado** agrega solo las cuentas `saving`; las metas **no** modifican el saldo total.

### ADR-13 — Mensualidades/suscripciones (v0.6)
- **Decisión:** una **mensualidad** (`Subscription`) es un compromiso periódico de fecha a fecha; el progreso se mide por tiempo transcurrido (0–100%) y su estado deriva de la fecha (próxima / activa / finalizada).
- **Renovación:** crea una operación de egreso ("pago") marcada como pagada sobre la cuenta elegida (resta saldo) y recicla la mensualidad para el período siguiente (mismo largo). Renovable en los últimos 7 días o al vencer.

### ADR-14 — Notificaciones in-app (v0.6)
- **Decisión:** notificaciones generadas **al consultar** (`GET /api/notifications`) evaluando el estado actual del dominio (vencimientos próximos, operaciones vencidas, metas alcanzadas), deduplicadas por `kind` + referencia.
- **Efecto:** sin jobs programados; el estado cambia al abrir la app. Las alertas se marcan como leídas sin regenerarse.

### ADR-15 — Asistente IA (planificado v0.7)
- **Decisión:** asistente conversacional que responde sobre los **datos del propio usuario** (saldos, gastos, metas) con respuestas ancladas a su contexto real — nunca respuestas genéricas.
- **Efecto:** para seguridad/privacidad, el backend genera un **resumen agregado del dominio** del usuario y lo envía al modelo, sin exponer credenciales ni datos de otros usuarios. Plan en `docs/AI-ASSISTANT.md`.

---

## 5. Requisitos funcionales (MVP)

### 5.1 Cuentas y sesión
- RF-01 Registro con email + contraseña y confirmación de email.
- RF-02 Login/logout seguro con sesiones de larga duración (refresh token).
- RF-03 Recuperación de contraseña por email.
- RF-04 Onboarding de registro: el usuario elige su **moneda base de visualización**.
- RF-05 Edición de perfil: nombre, moneda base, idioma (es-latino; estructura i18n preparada), zona horaria.

### 5.2 Monedero / cuentas de dinero
- RF-06 Crear "billeteras" (p. ej. Efectivo Bs, Efectivo USD, Banco X) con saldo inicial y moneda.
- RF-07 Editar/eliminar billeteras y ver saldo por billetera y total consolidado en USD.
- RF-08 **Ajuste manual del saldo** de una billetera (corrige errores o movimientos fuera de la app).

### 5.3 Cobros y pagos (núcleo)
- RF-09 Registrar una operación: `tipo` (cobro=ingreso / pago=egreso), `monto`, `moneda`, `concepto`, `persona/entidad`, `billetera`, `categoría`, `fecha`, `fecha_vencimiento` (opcional).
- RF-10 Estados de una operación: `pendiente`, `pagado`, `retrasado`, `cancelado`.
  - `pagado`: se registra la fecha real de pago y el saldo de la billetera se actualiza automáticamente (cobro suma, pago resta).
  - `retrasado`: transición automática cuando `fecha_vencimiento < hoy` y estado es `pendiente`.
- RF-11 Listar operaciones con filtros: estado, tipo, billetera, categoría, moneda, rango de fechas.
- RF-12 Marcar pendiente como pagada/cancelada con un tap; editar y eliminar operaciones (al editar/eliminar, la billetera se reajusta).
- RF-13 Detalle de operación mostrando monto original y equivalente en USD (con tasa de conversión usada).

### 5.4 Ahorro y metas
- RF-17 Crear una meta de ahorro: nombre, monto objetivo, moneda, fecha objetivo (opcional).
- RF-18 Registrar aportes a una meta (cantidad, moneda, billetera de origen).
- RF-19 Ver progreso: aportado vs objetivo, % de avance, días restantes (si hay fecha objetivo).

### 5.5 Atajos
- RF-20 Atajo desde el home para acciones frecuentes (p. ej. "Cobrar a María $20", "Pagar luz", "Aportar a vacaciones") en uno o dos taps.
- RF-21 Gestión de atajos: crear, reordenar y eliminar.

### 5.6 Home dashboard
- RF-22 Resumen de hoy: total por cobrar (pendientes), por pagar (pendientes), retrasados.
- RF-23 Saldo consolidado en USD y por billetera.
- RF-24 Tasa de conversión del día (dólar oficial BCV) visible y su fuente/fecha de actualización.
- RF-25 Próximos vencimientos (pagos pendientes de los próximos X días según la regla global de recordatorio).
- RF-26 **Recordatorio global configurable** (avisar N días antes de un vencimiento) + aviso específico por operación (`remind_me`).

### 5.7 Sistema de tasas
- RF-27 El backend consulta DolarApi con caché (TTL configurable, recom. 1 h) y guarda el histórico de tasas obtenidas en BD.
- RF-28 Fallback: si la API no responde, se usa la última tasa en caché marcándola como "desactualizada".
- RF-29 Tasa manual solo como última instancia de mantenimiento (no por operación): permite al usuario/operador fijar la tasa BCV a mano cuando la API no esté disponible.

---

## 6. Requisitos no funcionales

- RNF-01 **Seguridad:** HTTPS en producción, JWT de corta duración + refresh en cookie `httpOnly`, rate limiting en login/registro/recuperación, hash de contraseñas con bcrypt/argon2, sanitización de entradas, CORS restringido a orígenes conocidos.
- RNF-02 **Privacidad:** datos financieros sensibles; cifrado en reposo en BD; minimización de datos; no almacenar datos reales de tarjetas en MVP; política de privacidad y términos claros.
- RNF-03 **Precisión:** montos siempre como enteros en unidad mínima (céntimos) / `NUMERIC` en PostgreSQL; nunca flotantes para dinero.
- RNF-04 **PWA:** instalable, funciona offline parcialmente (caché de app shell y lectura), manifest y service worker, diseño mobile-first (también usable en desktop).
- RNF-05 **Rendimiento:** primera carga del dashboard < 3 s en 4G típico; consultas paginadas.
- RNF-06 **Portabilidad (RN):** lógica de negocio en paquetes TypeScript puros desacoplados de la UI, para reutilizar al migrar a React Native.
- RNF-07 **Contenedores:** 100% del stack de desarrollo en Docker Compose; sin instalar dependencias en la máquina local.
- RNF-08 **Mantenibilidad:** monorepo modular; estilo/lint definidos (ESLint + Prettier + Ruff); documentación mínima del repo.

---

## 7. Modelo de datos preliminar

> Borrador conceptual (se refina en fase de desarrollo). Multi-moneda requiere que cada monto se acompañe de su moneda y, si aplica, de su equivalencia en USD y la tasa usada.

- **users** — id, email (único, verificado), password_hash, nombre, moneda_base (elegida en onboarding), idioma, zona_horaria, recordatorio_dias (regla global), created_at, is_active.
- **wallets** — id, user_id, nombre, moneda, saldo_inicial, saldo (actual, actualizado automáticamente y ajustable a mano), tipo (efectivo/banco/otro), created_at.
- **contacts** (personas/entidades recurrentes) — id, user_id, nombre.
- **categories** — id, user_id (o predefinidas), nombre, icono, tipo (ingreso/egreso/transferencia).
- **transactions** — id, user_id, tipo (cobro/pago), estado (pendiente/pagado/retrasado/cancelado), monto (int menor unidad), moneda, monto_usd (int menor unidad), tasa_usd (decimal), fuente_tasa, concepto, contact_id (opcional), category_id, wallet_id (opcional), fecha, fecha_vencimiento (opcional), fecha_pagado (opcional), remind_me (bool), nota, created_at, updated_at.
  - **Índices:** (user_id, estado), (user_id, fecha_vencimiento), (user_id, fecha).
- **savings_goals** — id, user_id, nombre, monto_objetivo (int), moneda_objetivo, fecha_objetivo (opcional), created_at.
- **goal_contributions** — id, goal_id, monto (int), moneda, wallet_id (opcional), fecha, nota.
- **shortcuts** — id, user_id, etiqueta, acción/tipo objetivo (tipo de operación o meta), configuración (JSON), orden, icono.
- **exchange_rates** — id, fuente (oficial/paralelo/manual), compra/venta/promedio, fecha, retrieved_at. (Caché + histórico.)
- **email_verifications / password_resets** — tokens con expiración.

---

## 8. Riesgos y problemáticas a futuro (con mitigación)

| # | Riesgo | Descripción | Mitigación |
|---|---|---|---|
| R1 | **Precisión monetaria con flotantes** | Usar `float`/`double` para dinero genera errores de redondeo (inflaciÃ³n venezolana hace visibles los céntimos). | Guardar montos como enteros en la menor unidad; `NUMERIC` en PostgreSQL; nunca calcular saldos con flotantes. |
| R2 | **Múltiples tasas de dólar (BCV vs paralelo vs promedio)** | Dependiendo de la operación conviene una tasa u otra; cambiar de política luego es complejo. | Guardar TODA operación con su monto original + conversión USD + tasa usada + fuente al momento de registrar. La visualización puede cambiar, el dato vigilante queda. |
| R3 | **Dependencia de la API gratuita de tasas** | Puede caerse, cambiar de formato o tener límites de uso. | Caché con TTL, último valor conocido como fallback con marca "desactualizada", tasa manual configurable, integración como servicio desacoplado (interfaz + proveedor) por si hay que cambiar de fuente. |
| R4 | **Volatilidad/redondeo en conversiones** | Montos convertidos a USD pueden variar cada día. | Nunca recalcular el pasado; congelar la conversión en el momento de registro. Los reportes consolidados sí recalculan con la última tasa conocida. |
| R5 | **Vercel no ejecuta Python/Django** | Vercel es ideal para el frontend estático/PWA, pero no hospeda un servidor Django persistente. | Deploy: frontend en Vercel (y PWA); backend Django en un host compatible (Render / Railway / Fly.io) o elegir Supabase (Postgres+API alojada). Decisión en Fase 2. |
| R6 | **Migrar a React Native** | Acoplar lógica/estado a librerías web-only complica la reutilizaciÃ³n. | Arquitectura en capas: paquete de dominio + cliente API compartidos en TypeScript puro; UI desacoplada; estado global portable. PWA primero actúa como puente. |
| R7 | **Notificaciones y recordatorios** | PWA en iOS tiene soporte limitado/recién reciente de Web Push; recordatorios pueden no llegar. | Recordatorios como primera versión dentro de la app (badge/lista "hoy"); Web Push cuando el dispositivo lo soporte; roadmapp de notificaciones push nativas al portar. |
| R8 | **Zona horaria / retrasos automáticos** | El estado "retrasado" depende de "hoy" y de la zona horaria del usuario (Venezuela UTC-4). | Guardar zona_horaria por usuario; los cálculos de vencimiento se hacen en la zona del usuario; job programado (cron/APScheduler) para refrescar estados. Los retrasos también se calculan al consultar, no solo por cron. |
| R9 | **Errores de registro manual** | Tipeos/errores en montos y fechas degradan la confianza en los datos. | Validación estricta en frontend y backend (montos > 0, fechas coherentes), confirmación visual, ediciÃ³n/eliminaciÃ³n con historial simple, token de confirmaciÃ³n para acciones destructivas. |
| R10 | **Seguridad de datos financieros** | Robo de credenciales o filtración expone información sensible. | Auth robusta (JWT + refresh httpOnly, rate limit, confirmación de email), cifrado en reposo, jamás credenciales de banco (no hay conexión bancaria en MVP), backups, auditoría de accesos. |
| R11 | **Marca "Navi"** | Se detectó conflicto: `navi.com` es una fintech india de préstamos y `navi.app` una app de viajes IA activa (ago 2026). | **Resuelto parcialmente (ADR-07):** se adopta **NaviCash** como nombre comercial. Pendiente verificar `navicash.com`/`.app`, tiendas y redes; mantener lista de respaldo (Luca, Cobra, CuentaClara, Cashly, Pocketly, Finio). |
| R12 | **Multi-región futura** | Crecer a otros países implica nuevas monedas y formatos. | Modelo multi-moneda desde hoy (ADR-02); catálogo de monedas; el proveedor de tasas ya cubre América Latina (ve → ar/ch/mx/uy...) con la misma API. |
| R13 | **Crecimiento y costos** | Aumento de usuarios puede subir costos de BD/hosting. | Diseño eficiente desde el inicio, paginación e índices; elegir proveedores con plan escalable; monitoreo de costos en Fase 5/6. |

---

## 9. Arquitectura (implementada en Fase 3; decisiones en `docs/STACK.md`)

> **Stack aplicado (Fase 2 + 3):** Django 5.2 LTS + DRF, PostgreSQL 17, React 19 + TS + Vite + Tailwind v4 + shadcn/ui, PWA con `vite-plugin-pwa`, Docker Compose para desarrollo. Despliegue objetivo en Fase 5: Vercel (frontend) + Render (backend + Postgres).

```
Monorepo (Docker Compose para desarrollo)
├── apps/
│   └── web/            # React + TypeScript + Vite (PWA, mobile-first)
├── services/
│   └── api/            # Backend REST (candidatos: Django+DRF o Supabase+Edge)
├── packages/
│   ├── domain/         # Lógica de negocio y tipos compartidos (TS puro, portable a RN)
│   └── api-client/     # Cliente HTTP tipado para el frontend
├── infra/
│   └── docker-compose.yml  # postgres + api + web (dev)
└── docs/
```

- **BD:** PostgreSQL (verde para `NUMERIC`, extensiones, madurez, despliega bien con Supabase o RDS).
- **API REST:** Django + Django REST Framework O Supabase (Auth + PostgREST/Edge Functions). Decisión en Fase 2.
- **Frontend:** React + TypeScript + Vite; PWA (Workbox o vite-plugin-pwa); estado global (ver Fase 2); TanStack Query para datos.
- **Despliegue:** Frontend → Vercel. Backend → según elección (ver R5). BD → alojada (Supabase/RDS/Fly).

### Criterios de decisión de stack (Fase 2)
1. Velocidad de desarrollo del MVP. 2. Seguridad de auth y datos listas para usar. 3. Facilidad de pruebas. 4. Escalabilidad multi-región. 5. Costo y facilidad de despliegue (incluyendo "Vercel para el backend"). 6. Autonomía del equipo (Django a medida vs Supabase BaaS). 7. Portabilidad a React Native.

---

## 10. Preguntas abiertas (a resolver en nuevas sub-fases)
- [x] Confirmar disponibilidad de marca/dominio — **resuelto:** se adopta **NaviCash** (ADR-07). Pendiente verificar `navicash.*` y tiendas antes del despliegue.
- [x] Política de tasa por defecto — **resuelto:** BCV oficial siempre, sin selección por operación.
- [x] Saldos de billetera — **resuelto:** auto-actualización al marcar pagado + ajuste manual (ADR-08).
- [x] Recordatorios/avisos de vencimientos — **resuelto:** regla global configurable + opcional por operación (ADR-09).
- [x] Idioma de la UI — **resuelto:** español latino/neutro con estructura i18n (ADR-10).
- [x] Moneda base del usuario — **resuelto:** elegida por el usuario en el onboarding (ADR-10).

---

## 11. Roadmap de producto
- **v0.6 (actual):** transferencias entre cuentas (con tasa BCV/personalizada), billeteras de ahorro y cuentas afiliadas a metas, mensualidades con renovación, notificaciones in-app, total ahorrado en el dashboard; **124 tests en verde**.
- **v0.6.1 / hardening:** aplicar fixes de la auditoría de seguridad (`docs/AUDIT.md`): throttling, cookies seguras/HSTS, refresh con blacklist, secretos sin default, revocación por familia.
- **v0.7:** asistente IA conversacional (análisis del contexto del usuario, recomendaciones, "¿puedo permitirme X?").
- **v1:** cerrar testeo visual/E2E y seguridad, despliegue en producción (Vercel + Render), verificación de marca `navicash.*`, app instalable pulida.
- **v2:** tarjetas y cortes, importación CSV, informe mensual de ingresos/gastos.
- **v3:** notificaciones push nativas al portar a móvil, integración bancaria si la región lo permite con APIs abiertas.