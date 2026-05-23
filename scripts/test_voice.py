#!/usr/bin/env python
"""Qwen-Omni voice chat connectivity test"""

import io
import struct
import sys
import os
import wave
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "backend"))

# Load .env
from dotenv import load_dotenv
load_dotenv(PROJECT_DIR / ".env")


def make_silent_wav(duration_sec: float = 1.0, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    n_samples = int(sample_rate * duration_sec)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_samples)
    return buf.getvalue()


def test_text_only():
    from app.model_gateway.qwen_omni import QwenOmni
    omni = QwenOmni(model="qwen3-omni-flash")
    print(f"[OK] QwenOmni initialized: model={omni._model}, voice={omni._voice}")
    print("Testing text-only TTS...")
    try:
        result = omni.chat_with_text_only("推荐一款500元以内的蓝牙耳机")
        print(f"  text: {result['text'][:100]}")
        print(f"  audio: {len(result['audio_base64'])} chars base64")
        print(f"  voice: {result['voice']}")
        print(f"  tokens: in={result['tokens_input']}, out={result['tokens_output']}")
        print(f"  latency: {result['latency_ms']}ms")
        if result["text"]:
            print("[OK] Text-only test PASSED")
        else:
            print("[WARN] Got empty text response")
        return result
    except Exception as e:
        print(f"[FAIL] Text-only test: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_audio_input():
    from app.model_gateway.qwen_omni import QwenOmni
    omni = QwenOmni(model="qwen3-omni-flash")
    print("Testing audio input (silent WAV)...")
    audio = make_silent_wav(1.0)
    print(f"  Generated silent WAV: {len(audio)} bytes")
    try:
        result = omni.chat_with_audio(
            audio_bytes=audio,
            text="推荐一款蓝牙耳机",
        )
        print(f"  text: {result['text'][:100]}")
        print(f"  audio: {len(result['audio_base64'])} chars base64")
        print(f"  tokens: in={result['tokens_input']}, out={result['tokens_output']}")
        print(f"  latency: {result['latency_ms']}ms")
        if result["text"]:
            print("[OK] Audio input test PASSED")
        else:
            print("[WARN] No text (silent audio may produce empty result)")
        return result
    except Exception as e:
        print(f"[FAIL] Audio input test: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    print("Qwen-Omni Voice Test")
    print("=" * 50)
    test_text_only()
    print("-" * 50)
    test_audio_input()
