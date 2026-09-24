from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0005_alter_transaction_tasa_fuente'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='transaction',
            constraint=models.CheckConstraint(
                condition=models.Q(('tipo', 'transferencia'), _negated=True)
                | models.Q(monto_destino__gt=0),
                name='transaction_transfer_monto_destino_gt_0',
                violation_error_message='La transferencia debe indicar un monto destino mayor a cero.',
            ),
        ),
        migrations.AddConstraint(
            model_name='transaction',
            constraint=models.CheckConstraint(
                condition=models.Q(('tipo', 'transferencia'), _negated=True)
                | models.Q(tasa_uso__gt=0),
                name='transaction_transfer_tasa_uso_gt_0',
                violation_error_message='La transferencia debe indicar una tasa mayor a cero.',
            ),
        ),
    ]
