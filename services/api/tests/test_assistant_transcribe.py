"""tests — Transcripción de voz del asistente (endpoint + proveedores).

- ``POST /api/assistant/transcribe``: validación de multipart, auth y respuesta.
- ``OpenAITranscriber``: arma el multipart contra audio/transcriptions.
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

URL = "/api/assistant/transcribe"


def _audio(name="nota.mp4", data=b"fake-audio-bytes", content_type="audio/mp4"):
    """Clip de prueba (in-memory) para el multipart."""
    return SimpleUploadedFile(name, data, content_type=content_type)


@pytest.mark.django_db
class TestTranscriptionEndpoint:
    """Comportamiento HTTP del endpoint de transcripción."""

    def test_requires_auth(self) -> None:
        """Sin token la API responde 401."""
        client = APIClient()
        resp = client.post(URL, {"audio": _audio()}, format="multipart")
        assert resp.status_code == 401

    def test_missing_audio_rejected(self, api_client) -> None:
        """Falta el campo audio → 400 con detalle de validación."""
        resp = api_client.post(URL, {}, format="multipart")
        assert resp.status_code == 400
        assert "errors" in resp.data

    def test_empty_audio_rejected(self, api_client) -> None:
        """Audio sin contenido → 400."""
        resp = api_client.post(URL, {"audio": _audio(data=b"")}, format="multipart")
        assert resp.status_code == 400
        assert "errors" in resp.data

    def test_oversized_audio_rejected(self, api_client) -> None:
        """Clips de más de 10 MB se rechazan antes de llamar al proveedor."""
        big = b"x" * (10 * 1024 * 1024 + 1)
        resp = api_client.post(
            URL,
            {"audio": SimpleUploadedFile("grande.mp4", big, content_type="audio/mp4")},
            format="multipart",
        )
        assert resp.status_code == 400
        assert "errors" in resp.data

    def test_disallowed_extension_rejected(self, api_client) -> None:
        """Extensión que no es audio → 400 (se valida por nombre, no content-type)."""
        resp = api_client.post(URL, {"audio": _audio(name="a.txt", content_type="text/plain")}, format="multipart")
        assert resp.status_code == 400
        assert "errors" in resp.data

    def test_missing_extension_rejected(self, api_client) -> None:
        """Nombre sin extensión → 400."""
        resp = api_client.post(
            URL,
            {"audio": _audio(name="audio", content_type="audio/mp4")},
            format="multipart",
        )
        assert resp.status_code == 400
        assert "errors" in resp.data

    def test_octet_stream_content_type_accepted(self, api_client, monkeypatch) -> None:
        """Safari a veces manda el multipart como application/octet-stream.

        El content-type del navegador es poco fiable; con extensión válida el
        audio se acepta y el proveedor decide.
        """
        class FakeTranscriber:
            def transcribe(self, audio, filename):
                return "Registro un pago"

        monkeypatch.setattr("apps.assistant.services.get_transcriber", lambda: FakeTranscriber())
        resp = api_client.post(
            URL,
            {"audio": _audio(name="nota.mp4", content_type="application/octet-stream")},
            format="multipart",
        )
        assert resp.status_code == 200
        assert resp.data == {"transcript": "Registro un pago"}

    def test_empty_content_type_accepted(self, api_client, monkeypatch) -> None:
        """Sin content-type en el multipart, la extensión válida lo acepta."""
        class FakeTranscriber:
            def transcribe(self, audio, filename):
                return "Hola Navi"

        monkeypatch.setattr("apps.assistant.services.get_transcriber", lambda: FakeTranscriber())
        resp = api_client.post(
            URL,
            {"audio": _audio(name="nota.webm", content_type="")},
            format="multipart",
        )
        assert resp.status_code == 200
        assert resp.data == {"transcript": "Hola Navi"}

    def test_returns_transcript(self, api_client, monkeypatch) -> None:
        """Con un proveedor real (mockeado) devuelve el transcript en 200."""
        class FakeTranscriber:
            def transcribe(self, audio, filename):
                return "Registro un pago de veinte dólares"

        monkeypatch.setattr("apps.assistant.services.get_transcriber", lambda: FakeTranscriber())
        resp = api_client.post(URL, {"audio": _audio()}, format="multipart")
        assert resp.status_code == 200
        assert resp.data == {"transcript": "Registro un pago de veinte dólares"}

    def test_provider_failure_friendly(self, api_client, monkeypatch) -> None:
        """Si el proveedor falla, la API responde con mensaje legible (400)."""
        class FailingTranscriber:
            def transcribe(self, audio, filename):
                raise RuntimeError("boom")

        monkeypatch.setattr("apps.assistant.services.get_transcriber", lambda: FailingTranscriber())
        resp = api_client.post(URL, {"audio": _audio()}, format="multipart")
        assert resp.status_code == 400
        assert "detail" in resp.data

    def test_empty_transcript_friendly(self, api_client, monkeypatch) -> None:
        """Transcript vacío (proveedor devolvió nada) → mensaje legible."""
        class EmptyTranscriber:
            def transcribe(self, audio, filename):
                return "   "

        monkeypatch.setattr("apps.assistant.services.get_transcriber", lambda: EmptyTranscriber())
        resp = api_client.post(URL, {"audio": _audio()}, format="multipart")
        assert resp.status_code == 400
        assert "detail" in resp.data


@pytest.mark.django_db
class TestTranscriptionRateLimit:
    """El scope 'transcribe' limita las transcripciones por usuario."""

    def test_exceeds_limit(self, api_client, monkeypatch) -> None:
        """Después del límite, el endpoint devuelve 429."""
        from rest_framework.throttling import ScopedRateThrottle

        class FastTranscribeThrottle(ScopedRateThrottle):
            """Throttle de prueba: 2 peticiones por minuto en el scope."""

            scope = "transcribe"
            THROTTLE_RATES = {"transcribe": "2/minute"}

        from apps.assistant import views as assistant_views

        monkeypatch.setattr(
            assistant_views.TranscriptionView,
            "throttle_classes",
            [FastTranscribeThrottle],
        )

        statuses = []
        for _ in range(3):
            resp = api_client.post(URL, {"audio": _audio()}, format="multipart")
            statuses.append(resp.status_code)
        assert 429 in statuses


class TestOpenAITranscriber:
    """OpenAITranscriber arma el multipart correcto contra audio/transcriptions."""

    def test_posts_multipart_and_returns_text(self) -> None:
        """La llamada llega al endpoint con el modelo y devuelve el transcript."""
        from httpx import MockTransport, Request, Response

        from apps.assistant.providers import OpenAITranscriber

        captured: dict = {}

        def handler(request: Request) -> Response:
            captured["url"] = str(request.url)
            captured["auth"] = request.headers.get("Authorization", "")
            return Response(200, json={"text": "Registro un pago"})

        provider = OpenAITranscriber(
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
            transport=MockTransport(handler),
        )

        result = provider.transcribe(b"audio-bytes", "nota.mp4")

        assert result == "Registro un pago"
        assert "audio/transcriptions" in captured["url"]
        assert captured["auth"] == "Bearer sk-test"

    def test_raises_without_key(self, monkeypatch) -> None:
        """Sin clave configurada el proveedor se niega a llamar."""
        from apps.assistant.providers import OpenAITranscriber

        monkeypatch.delenv("AAI_API_KEY", raising=False)
        provider = OpenAITranscriber(api_key="")
        with pytest.raises(RuntimeError):
            provider.transcribe(b"audio", "nota.mp4")


def test_default_mock_transcriber(monkeypatch) -> None:
    """Sin AAI_API_KEY configurada el servicio usa el Mock determinista."""
    from apps.assistant.providers import MockTranscriber, get_transcriber

    monkeypatch.delenv("AAI_API_KEY", raising=False)
    monkeypatch.delenv("AAI_PROVIDER", raising=False)
    assert isinstance(get_transcriber(), MockTranscriber)
