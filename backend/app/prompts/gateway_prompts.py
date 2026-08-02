"""Model Gateway 层 Prompt 模板 — 语音 ASR / TTS 系统提示词。

模板常量集中定义，业务代码通过 getter 函数引用。
"""

from __future__ import annotations

# ============================================================
# QwenOmni — 语音转写 / 语音推荐 / TTS
# ============================================================

ASR_TRANSCRIBE_PROMPT = "请把这段语音逐字转写成文字，只输出转写结果，一个字都不要多。"

VOICE_RECOMMEND_USER_PROMPT = "请分析这段语音，帮我推荐合适的商品"

VOICE_RECOMMEND_SYSTEM = (
    "你是欧米，多模态购物智能体，致力于开启未来购物新范式。"
    "专精商品推荐、截图分析、购物对比。回复控制在 3-5 句话，活泼专业。"
)

TTS_SYSTEM = "你是欧米，购物智能体。用自然语速朗读以下内容。"

TTS_SYSTEM_FALLBACK = "你是欧米。用自然语速朗读以下内容。"


def get_asr_transcribe_prompt() -> str:
    """获取纯转写 prompt。"""
    return ASR_TRANSCRIBE_PROMPT


def get_voice_recommend_user_prompt() -> str:
    """获取语音推荐 user prompt。"""
    return VOICE_RECOMMEND_USER_PROMPT


def get_voice_recommend_system() -> str:
    """获取语音推荐 system prompt。"""
    return VOICE_RECOMMEND_SYSTEM


def get_tts_system() -> str:
    """获取 TTS system prompt。"""
    return TTS_SYSTEM


def get_tts_system_fallback() -> str:
    """获取 TTS 兜底 system prompt。"""
    return TTS_SYSTEM_FALLBACK
