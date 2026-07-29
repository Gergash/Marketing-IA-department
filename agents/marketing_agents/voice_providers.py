"""Generación de voz en off (voiceover): ElevenLabs (principal), OpenAI TTS y fal.ai (alternativas), mock.

Español es el idioma por defecto de narración (`settings.voice_language = "es"`).
A diferencia de `image_providers.generate_image` (que cae a un placeholder), un fallo real
de proveedor de voz DEBE propagar excepción: el spec exige que el run falle y no continúe
al ensamblado del timeline.
"""

from __future__ import annotations

import io
import uuid
import wave
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_STATIC_DIR = Path(__file__).resolve().parents[2] / "static" / "audio"
_WORDS_PER_SECOND = 2.5  # ritmo de habla estimado para narración en español


def _estimate_duration_seconds(text: str) -> float:
    """Estima la duración de narración por conteo de palabras (sin decodificar audio)."""
    words = len((text or "").split())
    return max(1.0, words / _WORDS_PER_SECOND)


def synthesize_voice(
    text: str,
    *,
    voice_provider: str | None = None,
) -> tuple[str, float]:
    """Devuelve (audio_url, duration_seconds) para el texto de narración dado."""
    from gateway.app.core.settings import get_settings

    s = get_settings()
    provider = (voice_provider or s.voice_provider).strip().lower()

    if provider == "elevenlabs" and s.elevenlabs_api_key:
        return _elevenlabs(text, s.elevenlabs_api_key, voice_id=s.elevenlabs_voice_id)
    if provider == "elevenlabs" and not s.elevenlabs_api_key:
        logger.error("voice.elevenlabs_missing_key")
        raise RuntimeError("voice_synth_failed:elevenlabs: missing API key")
    if provider == "openai" and s.openai_api_key:
        return _openai_tts(text, s.openai_api_key)
    if provider == "openai" and not s.openai_api_key:
        logger.error("voice.openai_missing_key")
        raise RuntimeError("voice_synth_failed:openai: missing API key")
    if provider == "fal" and s.fal_api_key:
        return _fal_tts(text, s.fal_api_key, model=s.fal_tts_model, voice=s.fal_tts_voice)
    if provider == "fal" and not s.fal_api_key:
        logger.error("voice.fal_missing_key")
        raise RuntimeError("voice_synth_failed:fal: missing API key")
    return _mock(text)


def _save_audio(raw: bytes, *, prefix: str, ext: str = "mp3") -> str:
    _STATIC_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{prefix}_{uuid.uuid4().hex}.{ext}"
    (_STATIC_DIR / filename).write_bytes(raw)
    return f"http://localhost:8000/static/audio/{filename}"


def _elevenlabs(text: str, api_key: str, *, voice_id: str) -> tuple[str, float]:
    """Genera voz vía API REST de ElevenLabs (modelo multilingüe, texto en español directo)."""
    import httpx

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    try:
        resp = httpx.post(
            url,
            json={"text": text, "model_id": "eleven_multilingual_v2"},
            headers={"xi-api-key": api_key, "Accept": "audio/mpeg"},
            timeout=60,
        )
        resp.raise_for_status()
        duration = _estimate_duration_seconds(text)
        audio_url = _save_audio(resp.content, prefix="elevenlabs")
        logger.info("voice.elevenlabs_generated", url=audio_url, duration_s=duration)
        return audio_url, duration
    except Exception as exc:
        logger.error("voice.elevenlabs_error", error=str(exc))
        raise RuntimeError(f"voice_synth_failed:elevenlabs: {exc}") from exc


def _openai_tts(text: str, api_key: str) -> tuple[str, float]:
    """Genera voz vía OpenAI TTS (texto en español directo al modelo)."""
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        resp = client.audio.speech.create(model="tts-1", voice="alloy", input=text)
        raw = resp.read() if hasattr(resp, "read") else resp.content
        duration = _estimate_duration_seconds(text)
        audio_url = _save_audio(raw, prefix="openai")
        logger.info("voice.openai_generated", url=audio_url, duration_s=duration)
        return audio_url, duration
    except Exception as exc:
        logger.error("voice.openai_error", error=str(exc))
        raise RuntimeError(f"voice_synth_failed:openai: {exc}") from exc


def _fal_tts(text: str, api_key: str, *, model: str, voice: str) -> tuple[str, float]:
    """Genera voz vía fal.ai (Kokoro Spanish u otro modelo TTS), reusando la misma FAL_API_KEY de imágenes."""
    import os

    import httpx

    os.environ.setdefault("FAL_KEY", api_key)

    try:
        import fal_client  # pip install fal-client
    except ImportError:
        logger.error("voice.fal_missing_sdk", hint="pip install fal-client")
        raise RuntimeError("voice_synth_failed:fal: fal_client not installed")

    try:
        result = fal_client.run(
            model,
            arguments={"prompt": text, "voice": voice},
        )
        audio_url: str = result["audio"]["url"]
        content_type = result["audio"].get("content_type", "")
        ext = "wav" if "wav" in content_type else "mp3"
        resp = httpx.get(audio_url, timeout=60, follow_redirects=True)
        resp.raise_for_status()
        duration = _estimate_duration_seconds(text)
        # Copia local para debug/dashboard; Shotstack usa la CDN de fal (sin ngrok).
        saved_url = _save_audio(resp.content, prefix="fal", ext=ext)
        logger.info(
            "voice.fal_generated",
            model=model,
            url=saved_url,
            cdn_url=audio_url[:80],
            duration_s=duration,
        )
        return audio_url, duration
    except Exception as exc:
        logger.error("voice.fal_error", error=str(exc))
        raise RuntimeError(f"voice_synth_failed:fal: {exc}") from exc


def _mock(text: str) -> tuple[str, float]:
    """Genera un WAV silencioso de duración estimada por conteo de palabras (dev sin proveedor real)."""
    duration = _estimate_duration_seconds(text)
    sample_rate = 8000
    n_frames = int(duration * sample_rate)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * n_frames)

    audio_url = _save_audio(buf.getvalue(), prefix="mock", ext="wav")
    logger.info("voice.mock_generated", url=audio_url, duration_s=duration)
    return audio_url, duration
