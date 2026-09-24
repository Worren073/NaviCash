from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rates', '0001_initial'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='exchangerate',
            constraint=models.CheckConstraint(
                condition=models.Q(compra__isnull=True) | models.Q(compra__gte=0),
                name='exchange_rate_compra_gte_0',
                violation_error_message='La compra no puede ser negativa.',
            ),
        ),
        migrations.AddConstraint(
            model_name='exchangerate',
            constraint=models.CheckConstraint(
                condition=models.Q(venta__isnull=True) | models.Q(venta__gte=0),
                name='exchange_rate_venta_gte_0',
                violation_error_message='La venta no puede ser negativa.',
            ),
        ),
        migrations.AddConstraint(
            model_name='exchangerate',
            constraint=models.CheckConstraint(
                condition=models.Q(promedio__isnull=True) | models.Q(promedio__gte=0),
                name='exchange_rate_promedio_gte_0',
                violation_error_message='El promedio no puede ser negativo.',
            ),
        ),
    ]
