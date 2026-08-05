"""exceptions — Formato de errores uniforme para la API.

Todos los errores devueltos por NaviCash usan la forma:

.. code-block:: json

   {
     "detail": "Mensaje legible para el usuario",
     "code": "codigo_máquina_opcional",
     "errors": { "campo": ["mensaje..."] }   // solo en validaciones
   }
"""

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler


class BusinessRuleError(APIException):
    """Error de regla de negocio (400) con mensaje legible.

    Ejemplos de uso: intentar pagar una operación ya pagada, moneda no soportada,
    saldo insuficiente para una acción, etc.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "No se pudo completar la operación."
    default_code = "business_rule_error"


def base_exception_handler(exc, context):
    """Handler global de excepciones que normaliza la respuesta de error.

    Args:
        exc: excepción lanzada (DRF, Django o propia).
        context: contexto de la request (dict).

    Returns:
        Response con el cuerpo ``{detail, code?, errors?}`` o None si DRF
        no puede manejarla (en ese caso se propaga al servidor).
    """
    response = exception_handler(exc, context)
    if response is None:
        return None

    detail = response.data
    if isinstance(detail, dict) and "detail" in detail:
        message = detail["detail"]
        code = getattr(exc, "default_code", None)
        errors = None
    else:
        # Error de validación de serializers: {campo: [msgs], non_field_errors: [...]}
        message = "Datos inválidos."
        code = "validation_error"
        errors = detail

    response.data = {
        "detail": str(message),
        "code": code,
        "errors": errors,
    }
    return response