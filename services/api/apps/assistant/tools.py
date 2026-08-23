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
