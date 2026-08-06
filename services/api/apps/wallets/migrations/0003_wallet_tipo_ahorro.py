from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wallets", "0002_wallet_color"),
    ]

    operations = [
        migrations.AlterField(
            model_name="wallet",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("cash", "Efectivo"),
                    ("bank", "Banco"),
                    ("saving", "Ahorro"),
                    ("other", "Otro"),
                ],
                default="cash",
                max_length=10,
                verbose_name="Tipo",
            ),
        ),
    ]
