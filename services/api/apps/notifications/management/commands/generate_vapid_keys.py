"""generate_vapid_keys — Genera el par de claves VAPID para Web Push.

Ejecutar UNA vez y guardar la salida como variables de entorno en Render
(VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY). La clave privada NUNCA va al repo.

    python manage.py generate_vapid_keys
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


def _b64url(raw: bytes) -> str:
    """Base64url sin padding (formato que esperan los navegadores)."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class Command(BaseCommand):
    """Imprime un par de claves VAPID P-256 listas para usar."""

    help = "Genera claves VAPID (público/privado) para Web Push."

    def handle(self, *args, **options) -> None:
        key = ec.generate_private_key(ec.SECP256R1())
        # Privada: entero de 32 bytes; pública: punto no comprimido (0x04|X|Y).
        private_raw = key.private_numbers().private_value.to_bytes(32, "big")
        public_raw = key.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        self.stdout.write(self.style.SUCCESS("Claves generadas (guárdalas ya):"))
        self.stdout.write(f"VAPID_PUBLIC_KEY={_b64url(public_raw)}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={_b64url(private_raw)}")
