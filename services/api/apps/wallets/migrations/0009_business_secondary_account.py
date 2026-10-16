"""Data migration: dota de DOS cuentas (principal + secundaria) a los negocios.

Para cada negocio existente:
- La billetera actual pasa a ``role="primary"`` y se renombra a
  ``"<nombre>-<MONEDA>"`` (misma moneda base del negocio).
- Se crea una cuenta ``secondary`` en la otra moneda (VES/USD), con saldo 0 y
  nombre ``"<nombre>-<MONEDA>"``.

Los pagos históricos se rellenan en la migración de ``crm`` (0013). Las monedas
de negocio quedan restringidas a VES/USD (una moneda antigua distinta se asume
USD para preservar el par de cuentas).
"""

from decimal import Decimal

from django.db import migrations

VALID_CURRENCIES = ("VES", "USD")


def _other(currency: str) -> str:
    return "USD" if currency == "VES" else "VES"


def forwards(apps, schema_editor):
    Business = apps.get_model("business", "Business")
    Wallet = apps.get_model("wallets", "Wallet")

    for business in Business.objects.all():
        currency = business.currency if business.currency in ("VES", "USD") else "USD"
        if currency != business.currency:
            business.currency = currency
            business.save(update_fields=["currency"])

        primary = Wallet.objects.filter(business_id=business.id, role="primary").first()
        if primary is None:
            primary = Wallet.objects.filter(business_id=business.id).order_by("created_at").first()
        if primary is not None:
            primary.role = "primary"
            if primary.currency not in ("VES", "USD"):
                primary.currency = currency
            primary.name = f"{business.name}-{primary.currency}"
            primary.save(update_fields=["role", "currency", "name"])
        else:
            Wallet.objects.create(
                user_id=business.user_id,
                business_id=business.id,
                name=f"{business.name}-{currency}",
                currency=currency,
                tipo="business",
                role="primary",
                saldo=Decimal("0.00"),
            )

        if not Wallet.objects.filter(business_id=business.id, role="secondary").exists():
            secondary_currency = _other(currency)
            Wallet.objects.create(
                user_id=business.user_id,
                business_id=business.id,
                name=f"{business.name}-{secondary_currency}",
                currency=secondary_currency,
                tipo="business",
                role="secondary",
                saldo=Decimal("0.00"),
            )


def backwards(apps, schema_editor):
    Wallet = apps.get_model("wallets", "Wallet")
    Wallet.objects.filter(role="secondary", business__isnull=False).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("wallets", "0008_wallet_role_alter_wallet_business_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
