"""views — ViewSet CRUD de atajos del usuario."""

from rest_framework import viewsets

from apps.core.permissions import IsOwner
from apps.shortcuts.models import Shortcut
from apps.shortcuts.serializers import ShortcutSerializer


class ShortcutViewSet(viewsets.ModelViewSet):
    """CRUD de atajos de la home (owner-scoped, ordenados por ``order``)."""

    serializer_class = ShortcutSerializer
    permission_classes = [IsOwner]

    def get_queryset(self):
        """Atajos del usuario autenticado en orden de prioridad."""
        return Shortcut.objects.filter(user=self.request.user)