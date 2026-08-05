"""managers — Managers (querysets) de los modelos de ``accounts``."""

from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Manager de ``User`` que usa ``email`` como identificador único.

    Sustituye al manager por defecto de Django (basado en ``username``).
    """

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields):
        """Crea y devuelve un usuario normalizando el email (minúsculas).

        Args:
            email: dirección de correo (se normaliza a minúsculas).
            password: contraseña en texto plano (se guarda hasheada); puede
                      ser None para usuarios sin contraseña.
            extra_fields: resto de campos (nombre, is_staff, etc.).

        Returns:
            Instancia de ``User`` persistida en BD.
        """
        if not email:
            raise ValueError("El email es obligatorio.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        """Crea un usuario normal (sin privilegios)."""
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str, **extra_fields):
        """Crea un superusuario (staff + superuser) para el admin."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser debe tener is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser debe tener is_superuser=True.")
        return self._create_user(email, password, **extra_fields)