# NaviCash — Asistente de IA (plan v0.7)

> Documento de diseño para el **asistente conversacional**. Define arquitectura,
> alcance, interacción con los datos del usuario, seguridad/privacidad y roadmap
> de implementación. Estado: **Fase 1 completa (backend + frontend + proveedor LLM)** (agosto 2026).

---

## 1. Objetivo

Un asistente conversacional integrado en la app que responde **sobre los datos reales del usuario** de NaviCash: saldos, gastos, cobros pendientes, metas de ahorro, mensualidades y tasa BCV. Sustituye la ambigüedad de respuestas genéricas por respuestas **ancladas al contexto del usuario**:

> "¿Cuánto llevo gastado este mes?" → calculado con sus transacciones.
> "¿Me puedo permitir X?" → ratio de gasto/ingreso con sus números.
> "¿Qué vence esta semana?" → vencimientos de su cuenta.

Fuera de alcance (v0.6/v0.7): consejo de inversión, órdenes bancarias, acceso a datos de terceros.

---

## 2. Principios de diseño

1. **El backend decide qué ve el modelo.** El asistente nunca recibe acceso directo a la BD ni a credenciales; el servidor le inyecta un **resumen agregado** del contexto del usuario (la misma lógica que `overview`/`savings`/`subscriptions`).
2. **Las respuestas se estilizan como sugerencias + datos**, no como consejos absolutos.
3. **Privacidad primero:** no se envían datos a servicios de terceros fuera del contexto mínimo del usuario autenticado.; los prompts no contienen credenciales, emails ni datos de otros usuarios.
4. **Fallback sin IA:** si el proveedor falla o el modelo no está disponible, se responde con cálculos internos (reglas deterministas) — el asistente nunca debe dejar de responder.
5. **Suposición mínima en el objetivo:** conversational con historial corto (últimos N mensajes), UI tipo chat.

---

## 3. Arquitectura propuesta

```
apps/web (React)
  └─ features/assistant/
       ├─ assistant-page.tsx      # pantalla de chat
       ├─ assistant-drawer.tsx    # acceso flotante desde el dashboard
       └─ hooks/use-assistant.ts  # conversación (mutación por mensaje)

services/api
  └─ apps/assistant/
       ├─ models.py               # ChatMessage (opcional persistir historial) ✅
       ├─ migrations/0001_initial.py # esquema ChatMessage ✅
       ├─ context.py              # build_context(user) → resumen del dominio ✅
       ├─ providers.py            # interfaz AssistantProvider (OpenAI/mock) ✅
       ├─ intent_rules.py         # fallback determinista (sin LLM) ✅
       ├─ services.py             # orquestación: contexto + proveedor + persistencia ✅
       ├─ serializers.py          # POST /api/assistant/messages { message } ✅
       ├─ views.py                # chat + history (scoped a request.user) ✅
       └─ urls.py                 # /api/assistant/messages, /history ✅
```

### 3.1 Capa de contexto (único contacto con los datos)

`context.build_context(user)` produce un dict JSONizable con:

```jsonc
{
  "base_currency": "USD",
  "rate": 91.5,                     // tasa oficial ya usada por overview
  "wallets": [ { "name": "Efectivo", "currency": "USD", "saldo": "120.00", "usd_value": "120.00" } ],
  "total_balance_usd": "1200.00",
  "to_receive": "150.00",  "to_pay": "200.00",  "overdue": "30.00",
  "recent_transactions": [ ... últimas 10 activas no sensibles ... ],
  "goals": [ { "name": "Vacaciones", "progress_percent": "55.0" } ],
  "savings_total": "500.00",
  "subscriptions": [ { "name": "Netflix", "days_remaining": 5 } ],
  "fin_month": { "income": "900.00", "expenses": "610.00" }
}
```

Reglas:
- Solo datos del `request.user`.
- Se reutilizan `overview.services.build_summary`, `savings` y `subscriptions` para no duplicar lógica.
- El contexto se **convierte a una prompt** con un system prompt fijo (idioma es, tono útil).

### 3.2 Orquestación (services.py)

1. El usuario envía `POST /api/assistant/messages { message, session_id? }`.
2. El backend valida el mensaje (longitud máxima, rate limit por usuario).
3. Construye `context = build_context(user)`.
4. Llama al `AssistantProvider` con: `system_prompt + context + historial reciente + mensaje`.
5. Valida + devuelve la respuesta (texto + sugerencias de acción opcionales).

**Fallback determinista:** si el proveedor falla, un conjunto de intents simples resuelven
preguntas comunes ("por cobrar", "por pagar", "vencidos", "meta X", "total ahorrado")
desde principios sin LLM.

La implementación ancla el flujo en `services.py:chat()`: valida, construye el
contexto con `build_context(user)`, delega en `get_provider()` (OpenAI si hay
clave, si no `MockAssistantProvider`) y, si el proveedor lanza excepción, cae a
`intent_rules.answer_deterministic`. El turno (user + assistant) se persiste bajo
un `session_id` (uuid) y queda disponible vía `GET /api/assistant/messages/history`.

---

## 4. Proveedores y seguridad

| Opción | Pros | Contras |
|---|---|---|
| **OpenAI (GPT-4o-mini / GPT-4.1-mini)** | Calidad buena, API simple, buen español | Costo por request (bajo con mini) |
| **Anthropic (Claude Haiku)** | Buenas para contexto financiero, safety | Ídem |
| **Google Gemini (flash)** | Gratis tier, rápido | Menor control finegranular |
| **Local (Ollama/llama.cpp)** | Privacidad total, cero externalización | Requiere HW; menor calidad |

Decisión recomendada: **OpenAI-compatible** con variable `AAI_PROVIDER=openai|anthropic|local`
y `AAI_API_KEY` en `.env` (nunca en el repo). El diseño desacoplado de `AssistantProvider`
permite cambiar sin tocar el resto.

**Seguridad en el pador:**
- `POST /api/assistant/messages` con `permission_classes=[IsAuthenticated]` (no `AllowAny`).
- Rate limit dedicado (p. ej. 30 mensajes/hora por usuario) + costo: `DEFAULT_THROTTLE`.
- **El contexto nunca incluye**: cookies, tokens, emails de contacto, `notes`, o datos de otros usuarios.
- Guard de **prompt injection**: los datos del usuario no son instrucciones; se envuelven en JSON y el sistema prompt instruye tratarlos solo como datos.
- `AssistantProvider` como clase; en dev un `DebugProvider` devuelve respuestas mock (sin red, para tests).

---

## 5. Alcance v0.7 (fase 1) — Minimal Viable Assistant

| Feature | Detalle | Estado |
|---|---|---|
| Chat simple | Drawer flotante + reseña de conversación en memoria/persistida | **Implementado (frontend + backend)** |
| Burbuja flotante "Navi" | Orbe translúcido con ojos, arrastrable a cualquier posición (localStorage), click abre el chat | **Implementado (frontend)** |
| 6+ intents determinizados como fallback | saldo, cobrar, pagar, vencidos, ahorro, metas, mensualidades, "¿me permito X?" | **Implementado (backend: `intent_rules.py`)** |
| Respuestas con datos reales | `build_context(user)` del backend (saldo, pendientes, metas, mensualidades, flujo del mes) | **Implementado (backend)** |
| Endpoint de chat | `POST /api/assistant/messages` autenticado + rate limit (scope `assistant`, `30/hour` configurable) | **Implementado (backend)** |
| Historial persistido | `ChatMessage` por sesión (`session_id`) + `GET /api/assistant/messages/history` scoped al usuario | **Implementado (backend)** |
| Persistencia del frontend | `use-assistant.ts` consume `POST /api/assistant/messages` (respuesta de Gemini) con fallback local | **Implementado** |
| Configuración por env | `AAI_PROVIDER`, `AAI_API_KEY`, `AAI_MODEL`, `AAI_BASE_URL`, `ASSISTANT_THROTTLE_RATE` | **Implementado (`.env.example`; activo con Gemini)** |
| Tests | contexto + fallback + rate limit + autenticación (sin llamadas externas) | **Implementado (17 nuevos, suite 141 passed)** |

**Hecho (agosto 2026) — frontend + conexión end-to-end:** `apps/web/src/features/assistant/navi-bubble.tsx` (burbuja con ojos, arrastre con pointer events, persistencia de posición) y `apps/web/src/features/assistant/assistant-chat.tsx` (panel glass con mensajes, animación de escritura y entrada). `apps/web/src/hooks/use-assistant.ts` consume `POST /api/assistant/messages` (envía `{ message, session_id }`, guarda la sesión devuelta y cae a la lógica determinista local si la llamada falla). Integrado en `apps/web/src/app/layout.tsx`. i18n `assistant.*`.

**Verificado end-to-end (agosto 2026):** respuesta real en español del proveedor **Gemini** (`gemini-3.5-flash-lite` vía endpoint OpenAI-compatible `generativelanguage.googleapis.com/v1beta/openai`) anclada al contexto del usuario, `session_id` persistido y CORS habilitado para `http://localhost:5173`. Typecheck del frontend en verde (host y contenedor).

**Hecho (agosto 2026) — backend (`services/api/apps/assistant/`):**
- `models.py`: `ChatMessage` (OwnedModel) + migración `0001_initial`.
- `context.py`: `build_context(user, today=None)` → dict JSONizable con saldo global (USD/VES), pendientes (to_receive/to_pay/overdue), próximos vencimientos, billeteras, flujo del mes, metas con progreso, mensualidades y recientes. Único contacto con los datos del usuario; no expone credenciales.
- `providers.py`: `AssistantProvider` (Protocol), `MockAssistantProvider` (fallback sin red) y `OpenAIProvider` (chat.completions compatible OpenAI, lee `AAI_*`).
- `intent_rules.py`: respuesta determinista de los intents comunes con datos reales.
- `services.py`: `chat()` orquesta y persiste el turno; `_load_history`/`_persist_chat` best-effort.
- `serializers.py`: validación del mensaje (≤1000 chars, no vacío) y respuesta.
- `views.py`: `ChatView` (POST, `IsAuthenticated` + `ScopedRateThrottle` scope `assistant`) y `ChatHistoryView` (GET scoped).
- `config/settings.py`: app registrada + `DEFAULT_THROTTLE_RATES.assistant = env("ASSISTANT_THROTTLE_RATE", "30/hour")` (cubre hallazgo A4 de `AUDIT.md`).
- `.env.example`: `AAI_PROVIDER`, `AAI_API_KEY`, `AAI_MODEL`, `AAI_BASE_URL`, `ASSISTANT_THROTTLE_RATE`.

**Nota de nomenclatura:** el doc original escribía `AAVID_*`; se usa `AAI_*` (asistente-inteligencia-artificial) conforme a §4.

### Fase 2 (tras v0.7)
- Sugerencias rápidas (chips), render de montos en moneda base.
- Invariabilidad de la respuesta del backend (markdown lite).
- "¿Me puedo permitir X?" con estadística simple (backend ya calcula `fin_month`).
- Recuperar el historial persistido por sesión en el frontend (`GET /api/assistant/messages/history`).
- Transféreb a WhatsApp/webhook y push (fase posterior).

---

## 6. BLOCKERS y dependencias

- Ninguna bloqueante. Dependencias blandas:
  - Aplicar primero **fixes de `AUDIT.md`** (rate limiting A4) para que la app delecite sin coste de bots.
  - Disponer de una clave de proveedor LLM para integración real (dev puede usar mock).

---

## 7. Tareas de implementación (orden sugerido)

- [x] 1. `apps/assistant/` con modelo esqueleto (mensajes de chat) + migración.
- [x] 2. `context.build_context(user)` + tests.
- [x] 3. `AssistantProvider` interfaz + `MockAssistantProvider` (tests) + `OpenAIProvider`.
- [x] 4. `views.py`/`serializers.py` (auth + rate limit) + tests.
- [x] 5. Fallback determinístico (`intent_rules.py`) + tests.
- [x] 6. Frontend: `features/assistant` (drawer + chat) + i18n.
- [x] 7. Wire `use-assistant.ts` al endpoint `POST /api/assistant/messages` (con fallback local si la llamada falla).
- [x] 8. Docs + `.env.example` (vars de la AI).