from django.db import migrations, models


def copy_name_to_first_last(apps, schema_editor):
    """Reparte el campo ``name`` (nombre completo) en ``first_name``/``last_name``."""
    User = apps.get_model("accounts", "User")
    for user in User.objects.all():
        parts = (user.name or "").strip().split(None, 1)
        user.first_name = parts[0] if parts else ""
        user.last_name = parts[1] if len(parts) > 1 else ""
        user.save(update_fields=["first_name", "last_name"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="first_name",
            field=models.CharField(blank=True, max_length=60, verbose_name="Nombre"),
        ),
        migrations.AddField(
            model_name="user",
            name="last_name",
            field=models.CharField(blank=True, max_length=60, verbose_name="Apellido"),
        ),
        migrations.AddField(
            model_name="user",
            name="phone",
            field=models.CharField(
                blank=True,
                help_text="Ej. +58 424 123 4567.",
                max_length=24,
                verbose_name="Teléfono",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="accepted_terms_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Términos aceptados el"),
        ),
        migrations.AddField(
            model_name="user",
            name="accepted_terms_version",
            field=models.CharField(blank=True, default="", max_length=20, verbose_name="Versión de términos"),
        ),
        migrations.RunPython(copy_name_to_first_last, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="user",
            name="name",
        ),
    ]
