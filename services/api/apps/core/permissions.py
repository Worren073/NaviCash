"""permissions — Permisos personalizados de DRF para NaviCash."""

from rest_framework.permissions import BasePermission


class IsOwner(BasePermission):
    """Permite el acceso solo al propietario del objeto.

    Los modelos del MVP heredan de ``apps.core.models.OwnedModel`` y, por
    tanto, tienen el atributo ``user``. Este permiso compara `obj.user` con el
    usuario autenticado. Para listar/crear se usa el default ``IsAuthenticated``.
    """

    message = "No tienes permiso para este recurso."

    def has_object_permission(self, request, view, obj) -> bool:
        """Devuelve True si el objeto pertenece al usuario autenticado."""
        return bool(request.user and request.user.is_authenticated and obj.user_id == request.user.id)