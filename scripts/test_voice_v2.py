"""Voice v2 integration test — ASR -> Agent Workflow -> TTS"""
import io, sys, wave
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

def make_silent_wav(duration_sec=1.0, sample_rate=16000):
    buf = io.BytesIO()
    n = int(sample_rate * duration_sec)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n)
    return buf.getvalue()

async def test_v2():
    from app.api.voice import voice_chat_v2
    from fastapi import UploadFile
    import io as _io

    audio = make_silent_wav(1.0)
    print(f"Audio: {len(audio)} bytes silent WAV")

    # Simulate UploadFile
    class FakeUpload:
        filename = "test.wav"
        content_type = "audio/wav"
        async def read(self):
            return audio

    print("Calling /api/voice/chat/v2 (with text, skip ASR)...")
    resp = await voice_chat_v2(FakeUpload(), "推荐一款500以内的蓝牙耳机")
    print(f"  transcribed: {resp.transcribed_text[:80]}")
    print(f"  answer: {resp.text[:120]}")
    print(f"  products: {len(resp.products)}")
    print(f"  decisions: {len(resp.decision_results)}")
    print(f"  evidence: {len(resp.evidence_list)}")
    print(f"  traces: {len(resp.trace_steps)}")
    print(f"  audio_url: {resp.audio_url[:60]}...")
    print(f"  fallback: {resp.fallback} ({resp.fallback_reason})")
    print(f"  latency: {resp.latency_ms}ms")

    if resp.text and resp.text != "抱歉，语音服务暂时不可用，请用文字告诉我你想买什么~":
        print("\n[OK] Voice v2 test PASSED")
    else:
        print("\n[FAIL] Got fallback response")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_v2())
