"""Replace uniq_wallet_name_per_user with partial unique index.

Revision ID: 0006
Revises: 0005
Create date: 2026-08-20
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wallets", "0005_balanceauditlog_alter_wallet_options_and_more"),
    ]

    operations = [
        # Remove the unconditional unique constraint
        migrations.RemoveConstraint(
            model_name="wallet",
            name="uniq_wallet_name_per_user",
        ),
        # Re-add it with a condition that excludes soft-deleted wallets
        migrations.AddConstraint(
            model_name="wallet",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_deleted=False),
                fields=["user", "name"],
                name="uniq_wallet_name_per_user",
            ),
        ),
    ]
