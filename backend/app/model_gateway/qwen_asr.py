"""Dedicated speech-to-text provider for DashScope's Qwen ASR endpoint."""

from __future__ import annotations

import time
import base64
from dataclasses import dataclass

import httpx

from app.core.config import settings


@dataclass(frozen=True)
class AsrResult:
    text: str
    model: str
    latency_ms: int


class QwenAsr:
    """Qwen3-ASR-Flash through DashScope's OpenAI-compatible chat endpoint.

    Qwen3-ASR is *not* Whisper-compatible: it accepts the audio as a Data URL
    in ``chat/completions``.  Posting multipart data to ``audio/transcriptions``
    happens to be accepted by some providers, but is a 404 on workspace-specific
    DashScope domains.  Keeping this provider dedicated prevents a future text
    gateway change from silently breaking mobile voice input again.
    """

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.asr_model
        self.base_url = settings.qwen_base_url.rstrip("/").replace("/api/v1", "/compatible-mode/v1")

    async def transcribe(self, audio_bytes: bytes, mime_type: str, filename: str = "recording") -> AsrResult:
        if not settings.qwen_api_key:
            raise RuntimeError("QWEN_API_KEY is not configured")
        t0 = time.perf_counter()
        timeout = httpx.Timeout(settings.asr_timeout)
        data_url = "data:{};base64,{}".format(
            mime_type, base64.b64encode(audio_bytes).decode("ascii")
        )
        payload = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [{"type": "input_audio", "input_audio": {"data": data_url}}],
            }],
            "stream": False,
            "asr_options": {"enable_itn": True},
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.qwen_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            response_payload = response.json()
        text = _extract_transcript(response_payload)
        if not text:
            raise RuntimeError("ASR returned an empty transcript")
        return AsrResult(text=text, model=self.model, latency_ms=round((time.perf_counter() - t0) * 1000))


def _extract_transcript(payload: dict) -> str:
    """Read the OpenAI-compatible chat-completion response defensively."""
    choices = payload.get("choices") or []
    message = choices[0].get("message") if choices and isinstance(choices[0], dict) else {}
    content = message.get("content") if isinstance(message, dict) else ""
    if isinstance(content, list):
        content = "".join(
            str(item.get("text") or item.get("content") or "")
            for item in content if isinstance(item, dict)
        )
    return str(content or payload.get("text") or payload.get("transcript") or "").strip()
