"""Qwen-Omni 全模态网关 — 音频输入 → 文字+语音输出。

两种调用方式:
1. 纯文本 TTS: OpenAI 兼容 API (stream) — 已验证通过
2. 音频+文本: DashScope 原生 multimodal API (stream SSE) — 同 Qwen-VL 模式

模型: qwen-omni-turbo / qwen3-omni-flash
输出: 文字 + 语音(base64 wav, 24kHz)
"""

import base64
import json
import logging
import time
from typing import Optional

import httpx
from openai import OpenAI

from app.core.config import QWEN_API_KEY, QWEN_BASE_URL

logger = logging.getLogger(__name__)

_OMNI_SYSTEM_PROMPT = (
    "你是豆仔，字节跳动旗下的智能购物导购助手（豆包之弟）。"
    "你能听懂语音，能看图片，能用自然亲切的声音回复用户。"
    "你专精商品推荐、截图分析、购物对比，始终引导用户完成购买决策。"
    "回复控制在 3-5 句话，活泼专业，不做无依据的判断。"
)

_VOICES = ["Cherry", "Serena", "Ethan", "Chelsie"]
_OPENAI_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class QwenOmni:
    def __init__(self, model: str = "qwen-omni-turbo", voice: str = "Cherry"):
        self._model = model
        self._voice = voice if voice in _VOICES else "Cherry"
        self._api_key = QWEN_API_KEY
        self._base_url = QWEN_BASE_URL.rstrip("/")
        # OpenAI-compatible client (for text-only TTS)
        self._openai = OpenAI(api_key=QWEN_API_KEY, base_url=_OPENAI_BASE)

    # ============================================================
    # 方式 1: 纯文本 → 文字+语音（OpenAI 兼容 API，已验证通过）
    # ============================================================

    def chat_with_text_only(self, text: str, system: str = "") -> dict:
        """纯文本对话 + TTS 语音输出"""
        messages = [
            {"role": "system", "content": system or _OMNI_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]

        t0 = time.perf_counter()
        text_response = ""
        audio_data = ""
        usage = {}

        try:
            completion = self._openai.chat.completions.create(
                model=self._model,
                messages=messages,
                modalities=["text", "audio"],
                audio={"voice": self._voice, "format": "wav"},
                stream=True,
                stream_options={"include_usage": True},
                timeout=120.0,
            )
            for chunk in completion:
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
            logger.error(f"Qwen-Omni text-only error: {e}")
            raise

        return self._build_result(text_response, audio_data, usage, t0)

    # ============================================================
    # 方式 2: 音频输入 → 文字+语音（DashScope 原生 multimodal API）
    # ============================================================

    def chat_with_audio(
        self,
        audio_bytes: bytes,
        text: str = "",
        system: str = "",
    ) -> dict:
        """发送音频+文字，流式返回文字和语音。

        使用 DashScope 原生 multimodal-generation API（SSE 流式）。
        音频以 base64 data URI 传入，与 Qwen-VL 图片同模式。
        """
        audio_b64 = base64.b64encode(audio_bytes).decode()
        audio_uri = f"data:audio/wav;base64,{audio_b64}"

        # 构建 multimodal content
        content = []
        if text:
            content.append({"text": text})
        else:
            content.append({"text": "请分析这段语音，帮我推荐合适的商品"})
        content.append({"audio": audio_uri})

        system_prompt = system or _OMNI_SYSTEM_PROMPT

        messages = [
            {"role": "system", "content": [{"text": system_prompt}]},
            {"role": "user", "content": content},
        ]

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
            with httpx.stream(
                "POST",
                f"{self._base_url}/services/aigc/multimodal-generation/generation",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "X-DashScope-SSE": "enable",
                },
                json=payload,
                timeout=120.0,
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
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
                        # 文字内容
                        ct = msg.get("content", [])
                        for part in ct if isinstance(ct, list) else [ct]:
                            if isinstance(part, dict):
                                if "text" in part:
                                    text_response += part["text"]
                                if "audio" in part:
                                    audio_data += part["audio"].get("data", "") or ""
                                    audio_data += part["audio"].get("transcript", "") or ""
                            elif isinstance(part, str):
                                text_response += part

                    # token 统计
                    if "usage" in output:
                        u = output["usage"]
                        usage = {
                            "input_tokens": u.get("input_tokens", 0),
                            "output_tokens": u.get("output_tokens", 0),
                        }

        except Exception as e:
            logger.error(f"Qwen-Omni audio error: {e}")
            raise

        return self._build_result(text_response, audio_data, usage, t0)

    def _build_result(self, text: str, audio_b64: str, usage: dict, t0: float) -> dict:
        return {
            "text": text.strip(),
            "audio_base64": audio_b64,
            "audio_format": "wav",
            "voice": self._voice,
            "tokens_input": usage.get("input_tokens", 0),
            "tokens_output": usage.get("output_tokens", 0),
            "latency_ms": round((time.perf_counter() - t0) * 1000),
        }
