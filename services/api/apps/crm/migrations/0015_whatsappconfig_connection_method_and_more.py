from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0014_product_kind"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappconfig",
            name="connection_method",
            field=models.CharField(
                choices=[
                    ("manual", "Manual"),
                    ("embedded_signup", "Embedded Signup"),
                    ("coexistence", "Coexistence"),
                ],
                default="manual",
                max_length=20,
                verbose_name="Método de conexión",
            ),
        ),
        migrations.AddField(
            model_name="whatsappconfig",
            name="business_app_connected",
            field=models.BooleanField(
                default=False,
                verbose_name="Conectado desde WhatsApp Business App (Coexistence)",
            ),
        ),
        migrations.AddField(
            model_name="whatsappconfig",
            name="meta_data",
            field=models.JSONField(
                blank=True, default=dict, verbose_name="Datos adicionales de Meta"
            ),
        ),
    ]
