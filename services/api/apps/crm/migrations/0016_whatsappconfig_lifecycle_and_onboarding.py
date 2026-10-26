from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0015_whatsappconfig_connection_method_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappconfig",
            name="token_type",
            field=models.CharField(
                blank=True,
                default="bearer",
                max_length=30,
                verbose_name="Tipo de token",
            ),
        ),
        migrations.AddField(
            model_name="whatsappconfig",
            name="token_expires_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Expiración del token",
            ),
        ),
        migrations.AddField(
            model_name="whatsappconfig",
            name="token_valid",
            field=models.BooleanField(
                default=True,
                verbose_name="Token válido",
            ),
        ),
        migrations.AddField(
            model_name="whatsappconfig",
            name="last_token_check_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Última verificación de token",
            ),
        ),
        migrations.AddField(
            model_name="whatsappconfig",
            name="onboarding_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pendiente"),
                    ("connected", "Conectado"),
                    ("reconnect_required", "Reconexión requerida"),
                    ("disconnected", "Desconectado"),
                ],
                default="connected",
                max_length=30,
                verbose_name="Estado de onboarding",
            ),
        ),
        migrations.AddField(
            model_name="whatsappconfig",
            name="webhook_subscribed",
            field=models.BooleanField(
                default=False,
                verbose_name="Webhook suscrito a WABA",
            ),
        ),
        migrations.AddField(
            model_name="whatsappconfig",
            name="quality_rating",
            field=models.CharField(
                blank=True,
                default="",
                max_length=32,
                verbose_name="Calificación de calidad",
            ),
        ),
        migrations.AddField(
            model_name="whatsappconfig",
            name="verified_name",
            field=models.CharField(
                blank=True,
                default="",
                max_length=120,
                verbose_name="Nombre verificado",
            ),
        ),
        migrations.AddField(
            model_name="whatsappconfig",
            name="messaging_limit_tier",
            field=models.CharField(
                blank=True,
                default="",
                max_length=64,
                verbose_name="Límite de mensajería",
            ),
        ),
    ]
