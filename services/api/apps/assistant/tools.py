"""tools — Definición y ejecutor de herramientas (function calling) para Navi.

Define las herramientas que el LLM puede invocar para consultar datos o
preparar registros.  La ejecución usa exclusivamente el ``context`` que
``build_context`` ya construye: NO ejecuta queries frescas a la BD.

Flujo:
1. El LLM decide qué tool llamar con los argumentos extraídos del mensaje.
2. ``execute_tool`` despacha al ejecutor correspondiente.
3. El resultado (dict plano) se retorna al LLM como contenido de la tool
   message para que genere la respuesta final al usuario.

Las tools de registro (``register_transaction``, ``create_transfer``) solo
generan un *preview* con status ``pending_confirmation``; la ejecución real
la orquesta ``services.chat`` vía cache + confirmación del usuario.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from apps.core.currency import round_money

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Definición de tools (formato OpenAI function calling)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "register_transaction",
            "description": (
                "Prepara el registro de un cobro (dinero recibido) o pago "
                "(dinero gastado) en una cuenta del usuario. Retorna un preview "
                "que requiere confirmación del usuario antes de ejecutarse."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tipo": {
                        "type": "string",
                        "enum": ["cobro", "pago"],
                        "description": (
                            "'cobro' si el usuario recibió dinero, "
                            "'pago' si gastó o pagó algo"
                        ),
                    },
                    "monto": {
                        "type": "number",
                        "description": "Monto numérico del movimiento",
                    },
                    "moneda": {
                        "type": "string",
                        "enum": ["USD", "VES", "EUR"],
                        "description": "Código de moneda (USD, VES o EUR)",
                    },
                    "wallet": {
                        "type": "string",
                        "description": (
                            "Nombre exacto de la cuenta (ej: "
                            "'Banco de Venezuela', 'Efectivo')"
                        ),
                    },
                    "concepto": {
                        "type": "string",
                        "description": (
                            "Descripción limpia y concisa del movimiento "
                            "(ej: 'Banesco', 'Servicio de luz', 'Trabajo')"
                        ),
                    },
                    "tasa": {
                        "type": "number",
                        "description": (
                            "Tasa de cambio personalizada (ej.: 36.5). "
                            "Solo se usa cuando la moneda difiere de la "
                            "cuenta. Si el usuario dice 'tasa del BCV', "
                            "NO la envíes aquí; usa 'tipo_tasa' en su lugar."
                        ),
                    },
                    "tipo_tasa": {
                        "type": "string",
                        "enum": ["bcv", "euro", "personalizada"],
                        "description": (
                            "'bcv' si el usuario quiere la tasa oficial del "
                            "BCV del dólar (contexto 'rate'), 'euro' si quiere "
                            "la tasa oficial del euro (contexto 'euro_rate'), "
                            "'personalizada' si el usuario dio un número. "
                            "Solo aplica cuando moneda != moneda de la cuenta."
                        ),
                    },
                },
                "required": ["tipo", "monto", "wallet"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_transfer",
            "description": (
                "Prepara una transferencia de dinero entre dos cuentas del "
                "usuario. Retorna un preview que requiere confirmación."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "monto": {
                        "type": "number",
                        "description": "Monto a transferir",
                    },
                    "moneda": {
                        "type": "string",
                        "enum": ["USD", "VES", "EUR"],
                        "description": "Moneda del monto",
                    },
                    "source_wallet": {
                        "type": "string",
                        "description": "Nombre de la cuenta de origen",
                    },
                    "dest_wallet": {
                        "type": "string",
                        "description": "Nombre de la cuenta de destino",
                    },
                    "concepto": {
                        "type": "string",
                        "description": "Concepto de la transferencia",
                    },
                },
                "required": ["monto", "source_wallet", "dest_wallet"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_balance",
            "description": (
                "Consulta el saldo de una cuenta específica o el total de "
                "todas las cuentas del usuario."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "wallet": {
                        "type": "string",
                        "description": (
                            "Nombre de la cuenta (vacío u omitido para el total)"
                        ),
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_transactions",
            "description": (
                "Consulta el historial de transacciones recientes del usuario."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tipo": {
                        "type": "string",
                        "enum": ["cobro", "pago"],
                        "description": "Filtrar por tipo (opcional)",
                    },
                    "wallet": {
                        "type": "string",
                        "description": "Filtrar por nombre de cuenta (opcional)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_subscriptions",
            "description": (
                "Lista las suscripciones del usuario con estado y días "
                "restantes."
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_savings_goals",
            "description": "Lista las metas de ahorro del usuario con progreso.",
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_afford",
            "description": (
                "Verifica si el usuario puede costear un gasto dado su saldo "
                "actual en sus cuentas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "monto": {
                        "type": "number",
                        "description": "Monto que el usuario quiere gastar",
                    },
                    "moneda": {
                        "type": "string",
                        "enum": ["USD", "VES", "EUR"],
                        "description": "Moneda del gasto",
                    },
                },
                "required": ["monto", "moneda"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Definición de tools de NEGOCIO (formato OpenAI function calling, solo lectura)
# ---------------------------------------------------------------------------

TOOLS_BUSINESS = [
    {
        "type": "function",
        "function": {
            "name": "get_business_cashflow",
            "description": (
                "Flujo de caja del negocio: saldo actual, ingresos y egresos del "
                "mes, KPIs (ingresos/egresos del período, margen %) y la serie "
                "mensual de P&L."
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_receivables",
            "description": (
                "Cuentas por cobrar del negocio: total por cobrar, cartera "
                "vencida, antigüedad (aging) y facturas abiertas con sus saldos."
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_payables",
            "description": (
                "Cuentas por pagar del negocio: total por pagar y pedidos con "
                "saldo pendiente."
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_inventory",
            "description": (
                "Inventario del negocio: número de productos, valor total a "
                "costo y productos de mayor valor."
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_low_stock",
            "description": (
                "Productos del negocio con existencias en o por debajo de su "
                "umbral de alerta (stock bajo)."
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_clients",
            "description": (
                "Mejores clientes y proveedores del negocio por monto pagado en "
                "el período."
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_open_invoices",
            "description": (
                "Facturas abiertas del negocio (por cobrar), incluyendo las "
                "vencidas y sus días de atraso."
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_whatsapp_health",
            "description": (
                "Salud y estado operativo de la línea de WhatsApp Business del "
                "negocio: calidad (GREEN/YELLOW/RED), límite diario de mensajes (tier), "
                "nombre comercial verificado por Meta y estado de suscripción del webhook."
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_chat_metrics",
            "description": (
                "Métricas de volumen y atención de clientes en WhatsApp: "
                "número de conversaciones abiertas y mensajes pendientes sin leer."
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "diagnose_whatsapp_connection",
            "description": (
                "Diagnóstico guiado y asistencia cuando el usuario tiene problemas "
                "para conectar WhatsApp, el token expiró, el webhook está desconectado "
                "o Meta rechaza la vinculación (Concierge de Onboarding)."
            ),
        },
    },
]

# ---------------------------------------------------------------------------
# Ejecutor principal
# ---------------------------------------------------------------------------


def execute_tool(name: str, args: dict, context: dict) -> dict:
    """Ejecuta una tool call y devuelve un dict plano con el resultado.

    Args:
        name: nombre de la función (``"get_balance"``, etc.).
        args: argumentos extraídos por el LLM.
        context: contexto del usuario (``build_context``).

    Returns:
        Dict serializable a JSON con el resultado de la operación.
    """
    dispatch = {
        "get_balance": _exec_balance,
        "get_transactions": _exec_transactions,
        "get_subscriptions": _exec_subscriptions,
        "get_savings_goals": _exec_savings_goals,
        "check_afford": _exec_afford,
        "register_transaction": _exec_register_preview,
        "create_transfer": _exec_transfer_preview,
        "get_business_cashflow": _exec_business_cashflow,
        "get_receivables": _exec_receivables,
        "get_payables": _exec_payables,
        "get_inventory": _exec_inventory,
        "get_low_stock": _exec_low_stock,
        "get_top_clients": _exec_top_clients,
        "get_open_invoices": _exec_open_invoices,
        "get_whatsapp_health": _exec_whatsapp_channel_health,
        "get_chat_metrics": _exec_chat_metrics,
        "diagnose_whatsapp_connection": _exec_onboarding_diagnose,
    }
    handler = dispatch.get(name)
    if handler is None:
        return {"error": f"Tool desconocida: {name}"}
    try:
        return handler(args, context)
    except Exception as exc:  # noqa: BLE001 — nunca crashear el loop
        logger.warning("Error ejecutando tool %s: %s", name, exc)
        return {"error": f"Error interno al procesar {name}"}


# ---------------------------------------------------------------------------
# Tools de consulta (solo lectura del context)
# ---------------------------------------------------------------------------


def _exec_balance(args: dict, context: dict) -> dict:
    """Saldo de una cuenta específica o total."""
    wallet_name = (args.get("wallet") or "").strip()
    wallets = context.get("wallets") or []

    if not wallet_name:
        return {
            "total_usd": context.get("total_balance_usd"),
            "total_ves": context.get("total_balance_ves"),
            "wallets": [
                {"name": w["name"], "saldo": w["saldo"], "currency": w["currency"]}
                for w in wallets
            ],
        }

    for w in wallets:
        if wallet_name.lower() in w["name"].lower():
            return {
                "name": w["name"],
                "saldo": w["saldo"],
                "currency": w["currency"],
            }
    return {"error": f"No encontré la cuenta '{wallet_name}'"}


def _exec_transactions(args: dict, context: dict) -> dict:
    """Historial de transacciones recientes (del context)."""
    txs = context.get("recent_transactions") or []
    tipo_filter = args.get("tipo")
    wallet_filter = (args.get("wallet") or "").strip().lower()

    filtered = txs
    if tipo_filter:
        filtered = [t for t in filtered if t.get("tipo") == tipo_filter]
    if wallet_filter:
        filtered = [
            t for t in filtered
            if wallet_filter in (t.get("wallet") or "").lower()
        ]

    return {"transactions": filtered[:10], "count": len(filtered)}


def _exec_subscriptions(args: dict, context: dict) -> dict:
    """Suscripciones del usuario."""
    return {"subscriptions": context.get("subscriptions", [])}


def _exec_savings_goals(args: dict, context: dict) -> dict:
    """Metas de ahorro."""
    return {"goals": context.get("goals", [])}


def _exec_afford(args: dict, context: dict) -> dict:
    """Verifica si el usuario puede costear un gasto."""
    monto = args.get("monto")
    moneda = args.get("moneda", "USD")
    if monto is None:
        return {"error": "Falta el monto"}

    try:
        monto_decimal = Decimal(str(monto))
    except (InvalidOperation, ValueError):
        return {"error": "Monto inválido"}
    if monto_decimal <= 0:
        return {"error": "El monto debe ser mayor a 0"}

    wallets = context.get("wallets") or []
    total = Decimal("0")
    matching_wallets = []

    for w in wallets:
        w_currency = w.get("currency", "USD")
        w_saldo = _safe_decimal(w.get("saldo", "0"))
        if w_currency == moneda:
            total += w_saldo
            matching_wallets.append({"name": w["name"], "saldo": w["saldo"]})

    can_afford = total >= monto_decimal
    return {
        "can_afford": can_afford,
        "requested": f"{monto_decimal:,.2f} {moneda}",
        "available": f"{total:,.2f} {moneda}",
        "wallets": matching_wallets,
    }


# ---------------------------------------------------------------------------
# Tools de NEGOCIO (solo lectura del context)
# ---------------------------------------------------------------------------


def _no_business() -> dict:
    """Respuesta estándar cuando el usuario no tiene negocio creado."""
    return {
        "error": "no_business",
        "message": "El usuario no tiene un negocio creado en NaviCash.",
    }


def _exec_business_cashflow(args: dict, context: dict) -> dict:
    """Flujo de caja del negocio (saldo, mes actual, KPIs y serie P&L)."""
    if not context.get("business"):
        return _no_business()
    kpis = context.get("kpis") or {}
    return {
        "saldo": context.get("saldo"),
        "currency": context.get("currency"),
        "ingresos_mes": context.get("ingresos_mes"),
        "egresos_mes": context.get("egresos_mes"),
        "income_period": kpis.get("incomePeriod"),
        "expense_period": kpis.get("expensePeriod"),
        "margin_pct": kpis.get("marginPct"),
        "pnl": context.get("pnl") or [],
        "income_categories": context.get("income_categories") or [],
        "expense_categories": context.get("expense_categories") or [],
    }


def _exec_receivables(args: dict, context: dict) -> dict:
    """Cuentas por cobrar (total, vencido, aging y facturas abiertas)."""
    if not context.get("business"):
        return _no_business()
    kpis = context.get("kpis") or {}
    return {
        "receivable": kpis.get("receivable"),
        "overdue": kpis.get("overdue"),
        "currency": context.get("currency"),
        "aging": context.get("aging") or [],
        "open_invoices": context.get("open_invoices") or {},
    }


def _exec_payables(args: dict, context: dict) -> dict:
    """Cuentas por pagar (total y pedidos con saldo pendiente)."""
    if not context.get("business"):
        return _no_business()
    kpis = context.get("kpis") or {}
    return {
        "payable": kpis.get("payable"),
        "currency": context.get("currency"),
        "pending_orders": context.get("pending_orders") or {},
    }


def _exec_inventory(args: dict, context: dict) -> dict:
    """Inventario del negocio (número de productos, valor y top por valor)."""
    if not context.get("business"):
        return _no_business()
    return {"inventory": context.get("inventory") or {}}


def _exec_low_stock(args: dict, context: dict) -> dict:
    """Productos con stock bajo."""
    if not context.get("business"):
        return _no_business()
    return {"low_stock": context.get("low_stock") or []}


def _exec_top_clients(args: dict, context: dict) -> dict:
    """Mejores clientes y proveedores del período."""
    if not context.get("business"):
        return _no_business()
    return {
        "top_clients": context.get("top_clients") or [],
        "top_suppliers": context.get("top_suppliers") or [],
        "currency": context.get("currency"),
    }


def _exec_open_invoices(args: dict, context: dict) -> dict:
    """Facturas abiertas (por cobrar) con vencidas y días de atraso."""
    if not context.get("business"):
        return _no_business()
    return {"open_invoices": context.get("open_invoices") or {}}


def _exec_whatsapp_channel_health(args: dict, context: dict) -> dict:
    """Salud y límites de la línea de WhatsApp del negocio."""
    if not context.get("business"):
        return _no_business()
    channels = context.get("channels") or {}
    if not channels.get("whatsapp_connected"):
        return {
            "connected": False,
            "status": channels.get("status", "not_configured"),
            "reconnect_required": channels.get("reconnect_required", False),
            "message": (
                "WhatsApp no está conectado o requiere reconexión. "
                "El usuario puede conectarlo desde Negocio > Chats con Meta."
            ),
        }
    quality = channels.get("quality_rating") or "UNKNOWN"
    return {
        "connected": True,
        "status": channels.get("status", "connected"),
        "connection_method": channels.get("connection_method"),
        "verified_name": channels.get("verified_name", ""),
        "quality_rating": quality,
        "messaging_limit_tier": channels.get("messaging_limit_tier", "TIER_250"),
        "webhook_subscribed": channels.get("webhook_subscribed", False),
        "reconnect_required": channels.get("reconnect_required", False),
        "health_summary": (
            "Excelente" if quality == "GREEN"
            else "Precaución (revisar quejas/bloqueos)" if quality == "YELLOW"
            else "Crítico (en riesgo de baneo por Meta)" if quality == "RED"
            else "Normal"
        ),
    }


def _exec_chat_metrics(args: dict, context: dict) -> dict:
    """Métricas de volumen y atención de chats en WhatsApp."""
    if not context.get("business"):
        return _no_business()
    channels = context.get("channels") or {}
    return {
        "whatsapp_connected": channels.get("whatsapp_connected", False),
        "open_chats": channels.get("open_chats", 0),
        "unread_chats": channels.get("unread_chats", 0),
    }


def _exec_onboarding_diagnose(args: dict, context: dict) -> dict:
    """Diagnóstico inteligente de onboarding y resolución de incidencias con Meta."""
    if not context.get("business"):
        return _no_business()
    channels = context.get("channels") or {}
    connected = channels.get("whatsapp_connected", False)
    status = channels.get("status", "not_configured")
    reconnect = channels.get("reconnect_required", False)
    webhook_ok = channels.get("webhook_subscribed", False)

    steps = []
    if not connected and status == "not_configured":
        issue = "not_started"
        diagnosis = "El negocio aún no ha iniciado la vinculación con WhatsApp Business."
        steps = [
            "Ve a la pestaña Negocio > Chats en NaviCash.",
            "Selecciona 'Conectar WhatsApp' y acepta la casilla de Coexistencia.",
            "Haz clic en 'Conectar con Meta' e inicia sesión con la cuenta de Facebook administradora.",
            "Selecciona o crea tu cuenta comercial de WhatsApp (WABA) y vincula tu número telefónico.",
        ]
    elif reconnect or status == "reconnect_required":
        issue = "token_expired_or_invalid"
        diagnosis = "El token de acceso de Meta expiró o los permisos fueron revocados."
        steps = [
            "Abre la ventana de configuración de WhatsApp en NaviCash.",
            "Haz clic en el botón 'Reconectar con Meta' para renovar el token en un solo clic.",
            "Asegúrate de no haber cambiado la contraseña de la cuenta de Meta recientemente.",
        ]
    elif connected and not webhook_ok:
        issue = "webhook_pending"
        diagnosis = "La línea está conectada pero el webhook de recepción no está suscrito a tu WABA."
        steps = [
            "En el panel de WhatsApp de NaviCash, haz clic en 'Reintentar suscripción'.",
            "Verifica que tu cuenta de Meta Business tenga permisos de administrador sobre la WABA.",
        ]
    elif connected:
        issue = "healthy"
        diagnosis = "La conexión con WhatsApp está activa, el webhook suscrito y el token vigente."
        steps = ["Todo funciona correctamente. Puedes atender clientes y registrar pedidos."]
    else:
        issue = "unknown"
        diagnosis = f"Estado actual de la conexión: {status}."
        steps = ["Intenta reconectar la cuenta desde Negocio > Chats."]

    return {
        "issue": issue,
        "diagnosis": diagnosis,
        "recommended_steps": steps,
        "connected": connected,
        "quality_rating": channels.get("quality_rating"),
    }


# ---------------------------------------------------------------------------
# Tools de registro (preview — NO ejecutan nada)
# ---------------------------------------------------------------------------


def _exec_register_preview(args: dict, context: dict) -> dict:
    """Preview de registro: valida datos y retorna resumen para confirmación.

    Si la moneda declarada difiere de la de la cuenta (ej: USD en wallet VES),
    y el LLM NO trae tasa/tipo_tasa, retorna un resultado de
    status ``currency_mismatch`` en vez de ``pending_confirmation`` para que el
    LLM pregunte al usuario qué tasa usar.
    """
    tipo = args.get("tipo")
    monto_raw = args.get("monto")
    wallet_name = (args.get("wallet") or "").strip()
    moneda = (args.get("moneda") or "").strip().upper()
    concepto = (args.get("concepto") or "").strip()
    tasa_arg = args.get("tasa")
    tipo_tasa = (args.get("tipo_tasa") or "").strip().lower()

    if not tipo or tipo not in ("cobro", "pago"):
        return {"status": "error", "message": "Tipo inválido (debe ser 'cobro' o 'pago')"}
    if monto_raw is None:
        return {"status": "error", "message": "Falta el monto"}
    try:
        monto_dec = _safe_decimal(monto_raw)
    except Exception:
        return {"status": "error", "message": "Monto inválido"}
    if monto_dec <= 0:
        return {"status": "error", "message": "El monto debe ser mayor a 0"}
    if not wallet_name:
        return {"status": "error", "message": "Falta la cuenta"}
    if moneda and moneda not in ("USD", "VES", "EUR"):
        return {"status": "error", "message": f"Moneda inválida: {moneda}"}

    # Buscar wallet en context
    wallets = context.get("wallets") or []
    wallet = None
    for w in wallets:
        if wallet_name.lower() in w["name"].lower():
            wallet = w
            break
    if not wallet:
        available = ", ".join(w["name"] for w in wallets) or "ninguna"
        return {
            "status": "error",
            "message": f"No encontré la cuenta '{wallet_name}'. Disponibles: {available}",
        }

    # Usar moneda de la wallet si no se especificó
    wallet_currency = wallet.get("currency", "USD")
    if not moneda:
        moneda = wallet_currency

    # --- Cross-currency detection ---
    if moneda != wallet_currency:
        if tipo_tasa in ("bcv", "euro"):
            rate = _safe_decimal(
                context.get("rate") if tipo_tasa == "bcv" else context.get("euro_rate")
            )
            if rate <= 0:
                return {
                    "status": "error",
                    "message": (
                        "No hay tasa BCV disponible en el contexto. "
                        "Indica al usuario que intente más tarde."
                    ),
                }
            return _monto_converted_preview(
                tipo, monto_raw, moneda, wallet, concepto, rate, tipo_tasa,
            )
        elif tasa_arg is not None:
            rate = _safe_decimal(tasa_arg)
            if rate <= 0:
                return {"status": "error", "message": "La tasa debe ser mayor a 0"}
            return _monto_converted_preview(
                tipo, monto_raw, moneda, wallet, concepto, rate, "personalizada",
            )
        else:
            # Sin tasa: informar al LLM del mismatch para que pregunte.
            bcv_rate = context.get("rate")
            euro_rate = context.get("euro_rate")
            return {
                "status": "currency_mismatch",
                "monto": str(monto_raw),
                "moneda_solicitada": moneda,
                "moneda_cuenta": wallet_currency,
                "wallet": wallet["name"],
                "bcv_rate": bcv_rate,
                "euro_rate": euro_rate,
                "message": (
                    f"El usuario pidió registrar {monto_raw} {moneda} "
                    f"pero la cuenta '{wallet['name']}' está en {wallet_currency}. "
                    f"La tasa BCV del dólar es {bcv_rate} y la del euro es {euro_rate}. "
                    f"Pregunta si quiere usar la tasa del dólar (BCV), la del euro o una personalizada."
                ),
            }

    # --- Same currency: proceed as before ---
    return {
        "status": "pending_confirmation",
        "tipo": tipo,
        "monto": str(monto_raw),
        "moneda": moneda,
        "wallet": wallet["name"],
        "concepto": concepto or ("Gasto registrado" if tipo == "pago" else "Ingreso registrado"),
    }


def _monto_converted_preview(
    tipo, monto_raw, moneda_original, wallet, concepto, rate, tipo_tasa,
) -> dict:
    """Genera preview con conversión calculada (cross-currency)."""
    wallet_currency = wallet.get("currency", "USD")
    monto = _safe_decimal(monto_raw)

    if moneda_original == "USD":
        monto_final = round_money(monto * rate)
    else:
        monto_final = round_money(monto / rate)

    return {
        "status": "pending_confirmation",
        "tipo": tipo,
        "monto": str(monto_raw),
        "moneda": wallet_currency,
        "moneda_original": moneda_original,
        "wallet": wallet["name"],
        "concepto": concepto or ("Gasto registrado" if tipo == "pago" else "Ingreso registrado"),
        "convertir": True,
        "tasa": str(rate),
        "tipo_tasa": tipo_tasa,
        "monto_convertido": str(monto_final),
        "moneda_destino": wallet_currency,
        "conversion_preview": (
            f"{monto:,.2f} {moneda_original} → {monto_final:,.2f} {wallet_currency} "
            f"(tasa {tipo_tasa}: {rate})"
        ),
    }


def _exec_transfer_preview(args: dict, context: dict) -> dict:
    """Preview de transferencia: valida ambas wallets y retorna resumen."""
    monto_raw = args.get("monto")
    moneda = (args.get("moneda") or "").strip().upper()
    source_name = (args.get("source_wallet") or "").strip()
    dest_name = (args.get("dest_wallet") or "").strip()
    concepto = (args.get("concepto") or "").strip()

    if monto_raw is None:
        return {"status": "error", "message": "Falta el monto"}
    try:
        monto_dec = _safe_decimal(monto_raw)
    except Exception:
        return {"status": "error", "message": "Monto inválido"}
    if monto_dec <= 0:
        return {"status": "error", "message": "El monto debe ser mayor a 0"}
    if moneda and moneda not in ("USD", "VES", "EUR"):
        return {"status": "error", "message": f"Moneda inválida: {moneda}"}
    if not source_name or not dest_name:
        return {"status": "error", "message": "Faltan las cuentas de origen y destino"}

    wallets = context.get("wallets") or []

    source = None
    dest = None
    for w in wallets:
        if source_name.lower() in w["name"].lower():
            source = w
        if dest_name.lower() in w["name"].lower():
            dest = w

    if not source:
        return {"status": "error", "message": f"No encontré la cuenta de origen '{source_name}'"}
    if not dest:
        return {"status": "error", "message": f"No encontré la cuenta de destino '{dest_name}'"}
    if source["name"] == dest["name"]:
        return {"status": "error", "message": "Las cuentas de origen y destino son la misma"}

    if not moneda:
        moneda = source.get("currency", "USD")

    return {
        "status": "pending_confirmation",
        "monto": str(monto_raw),
        "moneda": moneda,
        "source_wallet": source["name"],
        "dest_wallet": dest["name"],
        "concepto": concepto,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_decimal(value) -> Decimal:
    """Convierte un string a Decimal de forma segura (0 en caso de error)."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")
