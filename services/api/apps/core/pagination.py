"""pagination — Paginación uniforme de la API de NaviCash."""

from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """Paginación por página con tamaño configurable por petición.

    - Tamaño por defecto: 25 (ajustable con ``?page_size=``).
    - Máximo permitido: 100 (evita peticiones abusivas).
    - El cliente recibe ``count``, ``next`` y ``previous`` en la respuesta.
    """

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100