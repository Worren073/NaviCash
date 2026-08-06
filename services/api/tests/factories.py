"""Factories de factory-boy para los tests de NaviCash.

Permiten crear objetos de prueba con valores sensatos sin repetir código:
``UserFactory``, ``WalletFactory``, ``CategoryFactory``, ``ContactFactory``,
``TransactionFactory``, ``SavingsGoalFactory``, ``ExchangeRateFactory``.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import factory
from django.utils import timezone

from apps.accounts.models import EmailVerification, User
from apps.rates.models import ExchangeRate
from apps.savings.models import GoalContribution, SavingsGoal
from apps.transactions.models import Category, Contact, Transaction
from apps.wallets.models import Wallet


class UserFactory(factory.django.DjangoModelFactory):
    """Crea un usuario activo (sin verificación previa) con contraseña fija."""

    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "test-password-123")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    base_currency = "USD"
    is_active = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Usa el manager de usuarios para que el email se normalice."""
        manager = model_class._default_manager
        return manager.create_user(*args, **kwargs)


class VerifiedUserFactory(UserFactory):
    """Usuario activo que además ya pasó la verificación de email."""


class EmailVerificationFactory(factory.django.DjangoModelFactory):
    """Token de verificación fresco para un usuario (inactivo)."""

    class Meta:
        model = EmailVerification

    user = factory.SubFactory(UserFactory)
    token = factory.Sequence(lambda n: f"token-{n}-{n}-{n}")
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(hours=24))
    used = False


class WalletFactory(factory.django.DjangoModelFactory):
    """Billetera en USD con saldo inicial."""

    class Meta:
        model = Wallet

    user = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f"Billetera {n}")
    currency = "USD"
    saldo = Decimal("0.00")
    tipo = "cash"


class CategoryFactory(factory.django.DjangoModelFactory):
    """Categoría de egreso por defecto (creada manualmente)."""

    class Meta:
        model = Category

    user = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f"Categoría {n}")
    icon = "tag"
    tipo = "egreso"
    is_default = False


class ContactFactory(factory.django.DjangoModelFactory):
    """Contacto del usuario."""

    class Meta:
        model = Contact

    user = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f"Contacto {n}")


class TransactionFactory(factory.django.DjangoModelFactory):
    """Operación pendiente en USD (tasa 1), con monto por defecto."""

    class Meta:
        model = Transaction

    user = factory.SubFactory(UserFactory)
    tipo = "pago"
    estado = "pendiente"
    monto = Decimal("50.00")
    moneda = "USD"
    monto_usd = Decimal("50.00")
    tasa_usd = Decimal("1")
    fuente_tasa = "usd"
    concepto = "Prueba"
    fecha = factory.LazyFunction(date.today)
    fecha_vencimiento = factory.LazyFunction(lambda: date.today() + timedelta(days=7))


class SavingsGoalFactory(factory.django.DjangoModelFactory):
    """Meta de ahorro en USD."""

    class Meta:
        model = SavingsGoal

    user = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f"Meta {n}")
    target_amount = Decimal("1000.00")
    currency = "USD"


class GoalContributionFactory(factory.django.DjangoModelFactory):
    """Aporte a una meta (misma moneda por defecto: USD)."""

    class Meta:
        model = GoalContribution

    user = factory.SubFactory(UserFactory)
    goal = factory.SubFactory(SavingsGoalFactory)
    amount = Decimal("100.00")
    currency = "USD"
    amount_goal_currency = Decimal("100.00")


class ExchangeRateFactory(factory.django.DjangoModelFactory):
    """Tasa oficial guardada (promedio = 100 VES/USD por defecto)."""

    class Meta:
        model = ExchangeRate

    source = "oficial"
    currency = "VES"
    compra = Decimal("98.00")
    venta = Decimal("102.00")
    promedio = Decimal("100.00")
    rate_date = factory.LazyFunction(timezone.now)
    is_stale = False