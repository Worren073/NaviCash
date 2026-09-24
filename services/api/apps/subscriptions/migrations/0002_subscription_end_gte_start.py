from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0001_initial'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='subscription',
            constraint=models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F('start_date')),
                name='subscription_end_gte_start',
                violation_error_message='La fecha de cierre no puede ser anterior al inicio.',
            ),
        ),
    ]
