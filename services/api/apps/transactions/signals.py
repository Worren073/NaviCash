"""signals — Señales de bootstrap de la app ``transactions``.

Crea las categorías por defecto del usuario al registrarse (post_save de
``User``), para que el onboarding ya tenga categorías útiles.
"""

from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import User
from apps.transactions.models import Category

#: Categorías por defecto (ingresos y egresos) para usuarios nuevos.
DEFAULT_CATEGORIES = [
    ("Sueldo", "wallet", "ingreso"),
    ("Venta", "shopping-bag", "ingreso"),
    ("Cobro", "hand-coins", "ingreso"),
    ("Comida", "utensils", "egreso"),
    ("Transporte", "bus", "egreso"),
    ("Vivienda", "home", "egreso"),
    ("Servicios", "zap", "egreso"),
    ("Salud", "heart-pulse", "egreso"),
    ("Educación", "graduation-cap", "egreso"),
    ("Ocio", "gamepad-2", "egreso"),
    ("Otros", "tag", "egreso"),
]


@receiver(post_save, sender=User)
def bootstrap_default_categories(sender, instance, created: bool, **kwargs) -> None:
    """Si el usuario acaba de crearse, le asigna las categorías por defecto.

    Args:
        sender: modelo ``User``.
        instance: usuario creado o guardado.
        created: True en el primer ``save``.
        kwargs: resto de argumentos de la señal (ignorados).
    """
    if not created:
        return
    Category.objects.bulk_create(
        [
            Category(user=instance, name=name, icon=icon, tipo=tipo, is_default=True)
            for name, icon, tipo in DEFAULT_CATEGORIES
        ]
    )