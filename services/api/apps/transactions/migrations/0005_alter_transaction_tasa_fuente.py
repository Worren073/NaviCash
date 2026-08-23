from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0004_alter_transaction_options_transaction_is_deleted_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='transaction',
            name='tasa_fuente',
            field=models.CharField(
                choices=[
                    ('oficial', 'Tasa oficial (BCV)'),
                    ('euro', 'Tasa oficial del Euro (BCV)'),
                    ('manual', 'Tasa personalizada'),
                ],
                default='manual',
                max_length=10,
                verbose_name='Fuente de la tasa',
            ),
        ),
    ]
