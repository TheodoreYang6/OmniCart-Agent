"""Voice input API: reliable ASR first, optional manual TTS second.

Audio is transcribed here and then sent through the normal recommendation SSE
endpoint by the client.  This module never owns a second chat/recommendation path.
"""

from __future__ import annotations

import base64
import logging
import re
import time

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.model_gateway.qwen_asr import QwenAsr
from app.model_gateway.qwen_omni import QwenOmni

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_AUDIO_SIZE_BYTES = 10 * 1024 * 1024
MAX_AUDIO_DURATION_MS = 5 * 60 * 1000
_omni: QwenOmni | None = None


def _get_omni() -> QwenOmni:
    global _omni
    if _omni is None:
        _omni = QwenOmni()
    return _omni


class TranscribeResponse(BaseModel):
    text: str
    fallback: bool = False
    latency_ms: int = 0
    detected_mime: str = ""
    duration_ms: int | None = None
    model: str = ""


@router.post("/api/voice/transcribe", response_model=TranscribeResponse)
async def voice_transcribe(audio: UploadFile = File(..., description="用户录音")):
    """Transcribe M4A/WebM/OGG/WAV/MP3 with verified container metadata."""
    started = time.perf_counter()
    content_length = audio.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_AUDIO_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="录音文件不能超过 10MB")

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await audio.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_AUDIO_SIZE_BYTES:
            raise HTTPException(status_code=413, detail="录音文件不能超过 10MB")
        chunks.append(chunk)
    audio_bytes = b"".join(chunks)
    if len(audio_bytes) < 800:
        return TranscribeResponse(text="", fallback=True, detected_mime=(audio.content_type or ""))

    detected_mime = _detect_audio_mime(audio_bytes)
    if not detected_mime:
        raise HTTPException(status_code=415, detail="不支持或损坏的录音格式，请使用 M4A、WebM、OGG、WAV 或 MP3")
    declared_mime = (audio.content_type or "").split(";", 1)[0].lower()
    if declared_mime and not _mime_compatible(declared_mime, detected_mime):
        raise HTTPException(status_code=415, detail="录音文件类型与内容不一致，请重新录制后发送")

    duration_ms = _wav_duration_ms(audio_bytes) if detected_mime == "audio/wav" else None
    if duration_ms and duration_ms > MAX_AUDIO_DURATION_MS:
        raise HTTPException(status_code=413, detail="录音时长不能超过 5 分钟")

    try:
        result = await QwenAsr().transcribe(audio_bytes, detected_mime, audio.filename or "recording")
        text = _clean_transcription(result.text)
        if _is_reliable_transcription(text):
            return TranscribeResponse(
                text=text,
                latency_ms=round((time.perf_counter() - started) * 1000),
                detected_mime=detected_mime,
                duration_ms=duration_ms,
                model=result.model,
            )
    except Exception as exc:  # preserve a usable fallback during provider incidents
        logger.warning("primary ASR failed: %s", exc)

    # Do not fall back to a conversational multimodal model here.  It can answer
    # the audio with assistant boilerplate rather than transcribing it, and an
    # automatic resend would then create a fake user message in the conversation.
    # A clear retry state is safer than an untrustworthy transcript.
    logger.info("ASR unavailable after dedicated provider attempt; refusing conversational fallback")
    return TranscribeResponse(
        text="", fallback=True,
        latency_ms=round((time.perf_counter() - started) * 1000),
        detected_mime=detected_mime, duration_ms=duration_ms,
    )


class TTSRequest(BaseModel):
    text: str
    voice: str = "Cherry"


@router.post("/api/voice/tts")
async def voice_tts(req: TTSRequest):
    """Manual text-readout endpoint. Clients must never auto-play its output."""
    text = req.text.strip()
    if len(text) < 2:
        raise HTTPException(422, "文本太短")
    try:
        result = await _get_omni().text_to_speech(text[:300], req.voice)
        if result.get("audio_base64"):
            return Response(
                content=base64.b64decode(result["audio_base64"]), media_type="audio/wav",
                headers={"Content-Disposition": "inline; filename=reply.wav", "X-Voice": result.get("voice", "")},
            )
    except Exception as exc:
        logger.error("TTS failed: %s", exc)
    raise HTTPException(500, "TTS 服务暂不可用")


def _detect_audio_mime(audio_bytes: bytes) -> str:
    head = audio_bytes[:32]
    if head.startswith(b"RIFF") and audio_bytes[8:12] == b"WAVE":
        return "audio/wav"
    if head.startswith(b"OggS"):
        return "audio/ogg"
    if head.startswith(b"\x1aE\xdf\xa3"):
        return "audio/webm"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "audio/mp4"
    if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        return "audio/mpeg"
    return ""


def _mime_compatible(declared: str, detected: str) -> bool:
    aliases = {
        "audio/m4a": "audio/mp4", "audio/x-m4a": "audio/mp4", "audio/x-wav": "audio/wav",
        "audio/wave": "audio/wav", "video/webm": "audio/webm",
    }
    return aliases.get(declared, declared) == detected


def _wav_duration_ms(audio_bytes: bytes) -> int | None:
    if len(audio_bytes) < 44:
        return None
    try:
        rate = int.from_bytes(audio_bytes[28:32], "little")
        data_offset = audio_bytes.find(b"data")
        if rate <= 0 or data_offset < 0 or data_offset + 8 > len(audio_bytes):
            return None
        return round(int.from_bytes(audio_bytes[data_offset + 4:data_offset + 8], "little") * 1000 / rate)
    except Exception:
        return None


def _clean_transcription(raw: str) -> str:
    """Remove only known Omni trailing boilerplate, never natural shopping words."""
    raw = (raw or "").strip()
    trailing = re.compile(
        r"(?:\s*[。！？.!]?\s*)(?:如果还有(?:其他|别的).*?|有(?:什么|任何)问题.*?|随时(?:告诉|联系)我.*?|感谢(?:使用|您的).*?)$",
        re.I,
    )
    return trailing.sub("", raw).strip()


def _is_reliable_transcription(text: str) -> bool:
    """Reject assistant-like provider output before it can enter a conversation.

    Some multimodal fallbacks occasionally answer the recording as a chat model
    (for example, "你好呀，如果还有语音需要转写…") instead of returning an ASR
    transcript.  Such text is worse than an empty result: it is then submitted
    as if the user had said it.  Keep this deliberately narrow so natural short
    requests such as "你好" and model-heavy shopping queries remain valid.
    """
    value = re.sub(r"\s+", "", text or "")
    if len(value) < 2:
        return False
    contamination = (
        "语音需要转写", "需要转写", "请提供音频", "无法转写", "作为语音助手",
        "我是欧米", "我是智能助手", "如果还有类似的语音", "随时告诉我",
        "感谢使用", "有任何问题", "请问有什么可以帮您",
    )
    if any(phrase in value for phrase in contamination):
        logger.warning("discarded contaminated ASR result: %s", value[:80])
        return False
    # A long greeting plus a generic service offer is also an assistant reply,
    # even if a provider changes the exact boilerplate wording.
    if len(value) > 18 and value.startswith(("你好", "您好", "嗨")) and any(
        phrase in value for phrase in ("可以帮你", "我可以", "需要帮助", "转写")
    ):
        logger.warning("discarded assistant-shaped ASR result: %s", value[:80])
        return False
    return True


@router.post("/api/voice/chat/v2")
async def voice_chat_v2_deprecated():
    raise HTTPException(410, "已废弃。请使用 /api/voice/transcribe → /api/recommend/stream")
