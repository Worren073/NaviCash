# NaviCash — Asistente de IA (plan v0.7)

> Documento de diseño para el **asistente conversacional**. Define arquitectura,
> alcance, interacción con los datos del usuario, seguridad/privacidad y roadmap
> de implementación. Estado: **plan adquirido, sin implementar**.

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
       ├─ models.py               # ChatMessage? (opcional persistir historial)
       ├─ context.py              # build_context(user) → resumen del dominio
       ├─ provider.py             # interfaz AssistantProvider (OpenAI/Claude/local)
       ├─ services.py             # orquestación: contexto + prompt + llamada
       ├─ serializers.py          # POST /api/assistant/chat { message }
       ├─ views.py                # chat / history (scoped a request.user)
       └─ urls.py
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

| Feature | Detalle |
|---|---|
| Chat simple | Drawer flotante + reseña de conversación en memoria/persistida |
| 6+ intents determinizados como fallback | saldo, cobrar, pagar, vencidos, ahorro, metas |
| Respuestas con datos reales | usando `build_context` |
| Configuración por env | `AAVID_PROVIDER`, `AAVID_API_KEY`, `AAVID_MODEL` |
| Tests | contexto + fallback + rate limit + autenticación (sin llamadas externas) |

### Fase 2 (tras v0.7)
- Historial persistido, sugerencias rápidas (chips), render de montos en moneda base.
- Invariabilidad de la respuesta (markdown lite).
- "¿Me puedo permitir X?" con estadística simple de ingreso/gasto.
- Transféreb a WhatsApp/webhook y push (fase posterior).

---

## 6. BLOCKERS y dependencias

- Ninguna bloqueante. Dependencias blandas:
  - Aplicar primero **fixes de `AUDIT.md`** (rate limiting A4) para que la app delecite sin coste de bots.
  - Disponer de una clave de proveedor LLM para integración real (dev puede usar mock).

---

## 7. Tareas de implementación (orden sugerido)

1. `apps/assistant/` con modelo esqueleto (mensajes de chat) + migración.
2. `context.build_context(user)` + tests.
3. `AssistantProvider` interfaz + `MockAssistantProvider` (tests) + `OpenAIProvider`.
4. `views.py`/`serializers.py` (auth + rate limit) + tests.
5. Fallback determinístico (`intent_rules.py`) + tests.
6. Frontend: `features/assistant` (drawer + chat) + i18n.
7. Wire con `useOverview`/`useWallets` para contexto del FAB.
8. Docs + `.env.example` (vars de la AI).