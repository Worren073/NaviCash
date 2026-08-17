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

import json
import logging
from decimal import Decimal, InvalidOperation

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
    """Preview de registro: valida datos y retorna resumen para confirmación."""
    tipo = args.get("tipo")
    monto_raw = args.get("monto")
    wallet_name = (args.get("wallet") or "").strip()
    moneda = (args.get("moneda") or "").strip().upper()
    concepto = (args.get("concepto") or "").strip()

    if not tipo or tipo not in ("cobro", "pago"):
        return {"status": "error", "message": "Tipo inválido (debe ser 'cobro' o 'pago')"}
    if monto_raw is None:
        return {"status": "error", "message": "Falta el monto"}
    if not wallet_name:
        return {"status": "error", "message": "Falta la cuenta"}

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
    if not moneda:
        moneda = wallet.get("currency", "USD")

    return {
        "status": "pending_confirmation",
        "tipo": tipo,
        "monto": str(monto_raw),
        "moneda": moneda,
        "wallet": wallet["name"],
        "concepto": concepto or ("Gasto registrado" if tipo == "pago" else "Ingreso registrado"),
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
