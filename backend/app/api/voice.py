"""语音导购 API — ASR 转写 + TTS 播报，解耦聊天链路。

流程: 录音 → ASR 转文字 → 填入输入框 → 走正常 SSE 聊天 → TTS 播报回复
"""

import base64
import logging
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.model_gateway.qwen_omni import QwenOmni

logger = logging.getLogger(__name__)
router = APIRouter()

_VOICE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "uploads" / "voice"
_VOICE_DIR.mkdir(parents=True, exist_ok=True)

_omni: QwenOmni | None = None


def _get_omni() -> QwenOmni:
    global _omni
    if _omni is None:
        _omni = QwenOmni()
    return _omni


# ============================================================
# ASR: 语音转文字
# ============================================================

class TranscribeResponse(BaseModel):
    text: str
    fallback: bool = False
    latency_ms: int = 0


@router.post("/api/voice/transcribe", response_model=TranscribeResponse)
async def voice_transcribe(audio: UploadFile = File(..., description="用户录音")):
    """语音转文字。上传录音，返回转写文字。空录音直接返回空。"""
    import time
    t0 = time.perf_counter()

    audio_bytes = await audio.read()
    if len(audio_bytes) < 500:
        # 太短的录音 = 没说话
        return TranscribeResponse(text="", fallback=True)

    # 检测音频是否静音：采样音频能量
    if _is_silent(audio_bytes):
        return TranscribeResponse(text="", fallback=True)

    omni = _get_omni()
    try:
        raw = await omni.transcribe(audio_bytes)
        text = _clean_transcription(raw)
        if text and len(text) >= 2:
            return TranscribeResponse(
                text=text,
                latency_ms=round((time.perf_counter() - t0) * 1000),
            )
    except Exception as e:
        logger.warning(f"ASR failed: {e}")

    return TranscribeResponse(text="", fallback=True)


# ============================================================
# TTS: 文字转语音
# ============================================================

class TTSRequest(BaseModel):
    text: str
    voice: str = "Cherry"


@router.post("/api/voice/tts")
async def voice_tts(req: TTSRequest):
    """文本转语音。返回 WAV 音频二进制。"""
    text = req.text.strip()
    if not text or len(text) < 2:
        raise HTTPException(422, "文本太短")

    # 截断到合理长度（TTS 不需要播全文）
    tts_text = text[:300]

    omni = _get_omni()
    try:
        result = await omni.text_to_speech(tts_text, req.voice)
        audio_b64 = result.get("audio_base64", "")
        if audio_b64:
            audio_wav = base64.b64decode(audio_b64)
            return Response(
                content=audio_wav,
                media_type="audio/wav",
                headers={
                    "Content-Disposition": "inline; filename=reply.wav",
                    "X-Voice": result.get("voice", ""),
                    "X-Latency-Ms": str(result.get("latency_ms", 0)),
                },
            )
    except Exception as e:
        logger.error(f"TTS failed: {e}")

    raise HTTPException(500, "TTS 服务暂不可用")


# ============================================================
# 清洗
# ============================================================

def _is_silent(audio_bytes: bytes) -> bool:
    """检测音频是否为空/无效录音。M4A/AAC/WebM 编码无法直接读 PCM，
    用文件大小判断：< 2KB 几乎不可能包含有效语音。"""
    return len(audio_bytes) < 2000


def _clean_transcription(raw: str) -> str:
    """去掉 ASR 模型混入的 AI 回复废话。

    qwen-omni-turbo 在转写时总会追加自己的回复（"如果还有其他..."）。
    策略：检测到任何 AI 语气词/连接词就截断。
    """
    if not raw:
        return ""
    raw = raw.strip()

    # 更全面的断句：中英文标点都分割
    for sep in ["。", "？", "！", "，", ".", "?", "!", "\n"]:
        raw = raw.replace(sep, "|||")
    fragments = raw.split("|||")

    ai_patterns = [
        "如果还有其他", "如果还有别的", "有什么可以", "有什么需要", "有什么问题",
        "随时告诉我", "随时联系", "还有什么", "请问还有什么", "有什么想法",
        "可以再问我", "都可以跟我说", "都可以问我", "都可以跟我", "都可以和我说",
        "我可以", "我能帮", "让我来", "让我帮", "我来帮", "我帮你", "帮您",
        "好的", "明白了", "收到", "了解了", "没问题", "可以的", "可以",
        "这是", "以下是", "以上是", "总结", "综上所述",
        "希望", "祝你", "欢迎", "感谢", "请随时",
    ]

    clean = []
    for f in fragments:
        f = f.strip()
        if not f:
            continue
        # 检查是否为 AI 回复开头（含人称代词 + 引导词）
        is_ai = (
            any(p in f for p in ai_patterns) and len(f) > 3
        ) or (
            len(f) > 8 and (
                f.startswith("如果") or f.startswith("你可以") or
                f.startswith("需要我") or f.startswith("让我") or
                f.startswith("请问") or f.startswith("有什么")
            )
        )
        if is_ai:
            break  # 从这里开始都是 AI 回复
        clean.append(f)

    result = " ".join(clean).strip()
    return result if result else raw[:30].strip()


# ============================================================
# 兼容旧端点
# ============================================================

@router.post("/api/voice/chat/v2")
async def voice_chat_v2_deprecated():
    """[已废弃] 请使用 /api/voice/transcribe + SSE 聊天 + /api/voice/tts 的组合。"""
    raise HTTPException(410, "已废弃。请使用 /api/voice/transcribe → SSE chat → /api/voice/tts")
