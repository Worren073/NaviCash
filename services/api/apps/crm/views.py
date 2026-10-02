"""views — CRM del negocio."""

from __future__ import annotations

from django.db.models import Q
from rest_framework import viewsets

from apps.core.permissions import IsOwner
from apps.crm.models import BusinessContact
from apps.crm.serializers import BusinessContactSerializer


class BusinessContactViewSet(viewsets.ModelViewSet):
    """CRUD de clientes y proveedores del negocio."""

    serializer_class = BusinessContactSerializer
    permission_classes = [IsOwner]

    def get_queryset(self):
        """Contactos del usuario autenticado, con búsqueda opcional."""
        qs = BusinessContact.objects.filter(user=self.request.user).select_related("business")
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
                | Q(tax_id__icontains=search)
            )
        type_filter = self.request.query_params.get("type")
        if type_filter:
            qs = qs.filter(type=type_filter)
        return qs.order_by("name")
