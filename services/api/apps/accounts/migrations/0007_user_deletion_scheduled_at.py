from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_user_is_onboarded"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="deletion_scheduled_at",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "Momento en el que la cuenta y sus datos se purgan "
                    "definitivamente (derecho de eliminación). Null mientras "
                    "la cuenta esté activa; con valor, la cuenta está en "
                    "período de gracia cancelable."
                ),
                null=True,
                verbose_name="Eliminación programada el",
            ),
        ),
    ]
