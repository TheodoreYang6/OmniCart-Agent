"""Qwen-Omni 全模态网关 — 全异步。

三种调用:
1. ASR 语音转文字: 音频+prompt → 文字
2. TTS 文本转语音: 纯文本 → WAV 音频
3. 多模态对话: 音频+文本 → 文字+语音（已废弃，现用独立 ASR+TTS）
"""

import base64
import json
import logging
import time

import httpx
from openai import AsyncOpenAI

from app.core.config import QWEN_API_KEY, QWEN_BASE_URL

logger = logging.getLogger(__name__)

_VOICES = ["Cherry", "Serena", "Ethan", "Chelsie"]
# OpenAI 兼容地址从 QWEN_BASE_URL 派生（支持专属 MaaS 实例域名，不再硬编码公共云）
_OPENAI_BASE = QWEN_BASE_URL.rstrip("/").replace("/api/v1", "/compatible-mode/v1")

# 全局异步客户端
_http: httpx.AsyncClient | None = None
_openai: AsyncOpenAI | None = None


def _get_http() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(timeout=httpx.Timeout(120.0))
    return _http


def _get_openai() -> AsyncOpenAI:
    global _openai
    if _openai is None:
        _openai = AsyncOpenAI(api_key=QWEN_API_KEY, base_url=_OPENAI_BASE)
    return _openai


class QwenOmni:
    def __init__(self, model: str = "qwen-omni-turbo", voice: str = "Cherry"):
        self._model = model
        self._voice = voice if voice in _VOICES else "Cherry"
        self._api_key = QWEN_API_KEY
        self._base_url = QWEN_BASE_URL.rstrip("/")

    # ============================================================
    # ASR: 音频 → 文字（DashScope multimodal API）
    # ============================================================

    async def transcribe(self, audio_bytes: bytes, hint: str = "", mime_type: str = "audio/wav") -> str:
        """纯转写：音频 → 文字。prompt 要求只输出转写结果。"""
        from app.prompts.gateway_prompts import get_asr_transcribe_prompt
        prompt = hint or get_asr_transcribe_prompt()
        result = await self._call_multimodal(audio_bytes, prompt, system="", audio_mime=mime_type)
        return (result.get("text") or "").strip()

    async def transcribe_and_recommend(self, audio_bytes: bytes) -> dict:
        """转写并推荐：音频 → 文字回复 + 语音（保留旧兼容）。"""
        from app.prompts.gateway_prompts import (
            get_voice_recommend_system,
            get_voice_recommend_user_prompt,
        )
        return await self._call_multimodal(
            audio_bytes,
            get_voice_recommend_user_prompt(),
            system=get_voice_recommend_system(),
        )

    async def _call_multimodal(
        self, audio_bytes: bytes, text: str, system: str = "", audio_mime: str = "audio/wav",
    ) -> dict:
        """DashScope multimodal-generation API — 异步 SSE 流式。"""
        audio_b64 = base64.b64encode(audio_bytes).decode()
        audio_uri = f"data:{audio_mime};base64,{audio_b64}"

        content = [{"text": text}, {"audio": audio_uri}]
        messages = [
            {"role": "system", "content": [{"text": system}]} if system else None,
            {"role": "user", "content": content},
        ]
        messages = [m for m in messages if m is not None]

        payload = {
            "model": self._model,
            "input": {"messages": messages},
            "parameters": {
                "modalities": ["text", "audio"],
                "audio": {"voice": self._voice, "format": "wav"},
                "result_format": "message",
                "incremental_output": True,
            },
        }

        t0 = time.perf_counter()
        text_response = ""
        audio_data = ""
        usage = {}

        try:
            client = _get_http()
            async with client.stream(
                "POST",
                f"{self._base_url}/services/aigc/multimodal-generation/generation",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "X-DashScope-SSE": "enable",
                },
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    output = data.get("output", {})
                    choices = output.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        ct = msg.get("content", [])
                        for part in ct if isinstance(ct, list) else [ct]:
                            if isinstance(part, dict):
                                if "text" in part:
                                    text_response += part["text"]
                                if "audio" in part:
                                    audio_data += part["audio"].get("data", "") or ""
                            elif isinstance(part, str):
                                text_response += part
                    if "usage" in output:
                        u = output["usage"]
                        usage = {
                            "input_tokens": u.get("input_tokens", 0),
                            "output_tokens": u.get("output_tokens", 0),
                        }
        except Exception as e:
            logger.error(f"Qwen-Omni multimodal error: {e}")
            raise

        return {
            "text": text_response.strip(),
            "audio_base64": audio_data,
            "audio_format": "wav",
            "voice": self._voice,
            "tokens_input": usage.get("input_tokens", 0),
            "tokens_output": usage.get("output_tokens", 0),
            "latency_ms": round((time.perf_counter() - t0) * 1000),
        }

    # ============================================================
    # TTS: 文本 → 音频（OpenAI 兼容 API，异步）
    # ============================================================

    async def text_to_speech(self, text: str, voice: str = "") -> dict:
        """纯 TTS：文本 → WAV 音频。voice 为空则用默认。"""
        from app.prompts.gateway_prompts import get_tts_system
        v = voice if voice in _VOICES else self._voice
        messages = [
            {"role": "system", "content": get_tts_system()},
            {"role": "user", "content": text},
        ]

        t0 = time.perf_counter()
        text_response = ""
        audio_data = ""
        usage = {}

        try:
            client = _get_openai()
            completion = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                modalities=["text", "audio"],
                audio={"voice": v, "format": "wav"},
                stream=True,
                stream_options={"include_usage": True},
                timeout=120.0,
            )
            async for chunk in completion:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        text_response += delta.content
                    if hasattr(delta, "audio") and delta.audio:
                        audio_data += delta.audio.get("data", "") or ""
                if hasattr(chunk, "usage") and chunk.usage:
                    usage = {
                        "input_tokens": getattr(chunk.usage, "input_tokens", 0) or 0,
                        "output_tokens": getattr(chunk.usage, "output_tokens", 0) or 0,
                    }
        except Exception as e:
            logger.error(f"Qwen-Omni TTS error: {e}")
            raise

        return {
            "audio_base64": audio_data,
            "audio_format": "wav",
            "voice": v,
            "tokens_input": usage.get("input_tokens", 0),
            "tokens_output": usage.get("output_tokens", 0),
            "latency_ms": round((time.perf_counter() - t0) * 1000),
        }

    # ---- 旧兼容方法（同步包装，仅限非关键路径） ----

    def chat_with_audio(self, audio_bytes: bytes, text: str = "", system: str = "") -> dict:
        """[已废弃] 同步包装，仅供旧代码过渡。新代码请用 transcribe()。"""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._call_multimodal(audio_bytes, text, system))
        import nest_asyncio
        nest_asyncio.apply()
        return loop.run_until_complete(self._call_multimodal(audio_bytes, text, system))

    def chat_with_text_only(self, text: str, system: str = "") -> dict:
        """[已废弃] 同步包装。新代码请用 text_to_speech()。"""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._text_to_speech_sync_wrapper(text, system))
        import nest_asyncio
        nest_asyncio.apply()
        return loop.run_until_complete(self._text_to_speech_sync_wrapper(text, system))

    async def _text_to_speech_sync_wrapper(self, text: str, system: str) -> dict:
        from app.prompts.gateway_prompts import get_tts_system_fallback
        messages = [
            {"role": "system", "content": system or get_tts_system_fallback()},
            {"role": "user", "content": text},
        ]
        t0 = time.perf_counter()
        text_response = ""
        audio_data = ""
        try:
            client = _get_openai()
            completion = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                modalities=["text", "audio"],
                audio={"voice": self._voice, "format": "wav"},
                stream=True,
                stream_options={"include_usage": True},
                timeout=120.0,
            )
            async for chunk in completion:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        text_response += delta.content
                    if hasattr(delta, "audio") and delta.audio:
                        audio_data += delta.audio.get("data", "") or ""
        except Exception as e:
            logger.error(f"Qwen-Omni text-only error: {e}")
            raise
        return {
            "text": text_response.strip(),
            "audio_base64": audio_data,
            "audio_format": "wav",
            "voice": self._voice,
            "tokens_input": 0,
            "tokens_output": 0,
            "latency_ms": round((time.perf_counter() - t0) * 1000),
        }
