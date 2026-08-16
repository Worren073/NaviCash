"""tests — Transcripción de voz del asistente (endpoint + proveedores).

- ``POST /api/assistant/transcribe``: validación de multipart, auth y respuesta.
- ``OpenAITranscriber``: arma el multipart contra audio/transcriptions.
- ``GeminiTranscriber``: envía el audio en base64 a generateContent.
"""

from __future__ import annotations

import base64
import json

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

    def test_provider_auth_error_friendly(self, api_client, monkeypatch) -> None:
        """Error de clave del proveedor llega al usuario como mensaje claro."""
        from apps.assistant.providers import TranscriptionProviderError

        class AuthFailingTranscriber:
            def transcribe(self, audio, filename):
                raise TranscriptionProviderError("clave inválida", code="auth")

        monkeypatch.setattr("apps.assistant.services.get_transcriber", lambda: AuthFailingTranscriber())
        resp = api_client.post(URL, {"audio": _audio()}, format="multipart")
        assert resp.status_code == 400
        assert "clave" in resp.data["detail"].lower()

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
    monkeypatch.delenv("AAI_BASE_URL", raising=False)
    monkeypatch.delenv("AAI_MODEL", raising=False)
    assert isinstance(get_transcriber(), MockTranscriber)


class TestGeminiTranscriber:
    """GeminiTranscriber envía el audio en base64 a generateContent."""

    def test_posts_generate_content_and_returns_text(self) -> None:
        """La llamada llega a models/<model>:generateContent con inline_data."""
        from httpx import MockTransport, Request, Response

        from apps.assistant.providers import GeminiTranscriber

        captured: dict = {}

        def handler(request: Request) -> Response:
            captured["url"] = str(request.url)
            captured["auth"] = request.headers.get("x-goog-api-key", "")
            captured["payload"] = json.loads(request.read())
            return Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": "Registro un pago"}]}}]},
            )

        provider = GeminiTranscriber(
            api_key="gk-test",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            transport=MockTransport(handler),
        )

        result = provider.transcribe(b"audio-bytes", "nota.mp4")

        assert result == "Registro un pago"
        assert "models/gemini-2.0-flash:generateContent" in captured["url"]
        assert captured["auth"] == "gk-test"

        parts = captured["payload"]["contents"][0]["parts"]
        inline = next(p["inline_data"] for p in parts if "inline_data" in p)
        assert inline["mime_type"] == "audio/mp4"
        assert inline["data"] == base64.b64encode(b"audio-bytes").decode("ascii")

    def test_strips_openai_suffix_for_native_api(self, monkeypatch) -> None:
        """De la base OpenAI-compatible del chat se deriva la API nativa."""
        from httpx import MockTransport, Request, Response

        from apps.assistant.providers import GeminiTranscriber

        captured: dict = {}

        def handler(request: Request) -> Response:
            captured["url"] = str(request.url)
            return Response(200, json={"candidates": [{"content": {"parts": [{"text": "x"}]}}]})

        monkeypatch.setenv("AAI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
        provider = GeminiTranscriber(api_key="gk-test", transport=MockTransport(handler))
        provider.transcribe(b"audio", "nota.mp4")

        assert captured["url"].startswith(
            "https://generativelanguage.googleapis.com/v1beta/models/"
        )

    def test_uses_gemini_model_ignoring_whisper(self, monkeypatch) -> None:
        """Un AAI_TRANSCRIBE_MODEL=whisper-1 heredado no rompe el modelo de Gemini."""
        from httpx import MockTransport, Request, Response

        from apps.assistant.providers import GeminiTranscriber

        captured: dict = {}

        def handler(request: Request) -> Response:
            captured["url"] = str(request.url)
            return Response(200, json={"candidates": [{"content": {"parts": [{"text": "x"}]}}]})

        monkeypatch.setenv("AAI_TRANSCRIBE_MODEL", "whisper-1")
        monkeypatch.setenv("AAI_MODEL", "gemini-3.5-flash-lite")
        provider = GeminiTranscriber(api_key="gk-test", transport=MockTransport(handler))
        provider.transcribe(b"audio", "nota.mp4")

        assert "models/gemini-3.5-flash-lite:generateContent" in captured["url"]

    def test_raises_without_key(self, monkeypatch) -> None:
        """Sin clave configurada el proveedor se niega a llamar."""
        from apps.assistant.providers import GeminiTranscriber

        monkeypatch.delenv("AAI_API_KEY", raising=False)
        provider = GeminiTranscriber(api_key="")
        with pytest.raises(RuntimeError):
            provider.transcribe(b"audio", "nota.mp4")

    def test_maps_http_errors_to_codes(self) -> None:
        """Estado HTTP → TranscriptionProviderError con categoría para el mensaje."""
        from httpx import MockTransport, Request, Response

        from apps.assistant.providers import (
            GeminiTranscriber,
            TranscriptionProviderError,
        )

        def handler(request: Request) -> Response:
            return Response(403, json={"error": {"message": "API key not valid"}})

        provider = GeminiTranscriber(
            api_key="gk-test",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            transport=MockTransport(handler),
        )
        with pytest.raises(TranscriptionProviderError) as exc_info:
            provider.transcribe(b"audio", "nota.mp4")
        assert exc_info.value.code == "forbidden"


class TestTranscriberSelection:
    """get_transcriber elige el proveedor según la configuración de entorno."""

    def test_gemini_selected_for_generativelanguage(self, monkeypatch) -> None:
        """Base generativelanguage → se transcribe con Gemini."""
        from apps.assistant.providers import GeminiTranscriber, get_transcriber

        monkeypatch.setenv("AAI_API_KEY", "gk-test")
        monkeypatch.setenv("AAI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
        monkeypatch.setenv("AAI_MODEL", "gemini-3.5-flash-lite")
        assert isinstance(get_transcriber(), GeminiTranscriber)

    def test_gemini_selected_for_gemini_model(self, monkeypatch) -> None:
        """Modelo gemini → se transcribe con Gemini aunque la base sea OpenAI."""
        from apps.assistant.providers import GeminiTranscriber, get_transcriber

        monkeypatch.setenv("AAI_API_KEY", "gk-test")
        monkeypatch.setenv("AAI_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("AAI_MODEL", "gemini-3.5-flash-lite")
        assert isinstance(get_transcriber(), GeminiTranscriber)

    def test_openai_selected_for_openai_config(self, monkeypatch) -> None:
        """Sin Gemini en la config, una clave configurada usa OpenAI/Whisper."""
        from apps.assistant.providers import OpenAITranscriber, get_transcriber

        monkeypatch.setenv("AAI_API_KEY", "sk-test")
        monkeypatch.setenv("AAI_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("AAI_MODEL", "gpt-4o-mini")
        assert isinstance(get_transcriber(), OpenAITranscriber)
