"""Guardrails for ASR fallback output before it enters a user conversation."""

from app.api.voice import _is_reliable_transcription


def test_rejects_assistant_like_asr_fallback() -> None:
    assert not _is_reliable_transcription("你好呀，如果还有类似的语音需要转写，你可以随时告诉我。")
    assert not _is_reliable_transcription("作为语音助手，请提供音频后我才能转写。")


def test_keeps_natural_short_shopping_requests() -> None:
    assert _is_reliable_transcription("你好")
    assert _is_reliable_transcription("帮我找一款适合油皮的防晒，预算一百五")
    assert _is_reliable_transcription("iPhone 15 Pro 和 16 怎么选")
