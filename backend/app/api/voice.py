"""语音导购 API — 语音 → ASR → Agent Workflow → TTS

V1 (/api/voice/chat):    Qwen-Omni 端到端（已废弃，回答非豆仔）
V2 (/api/voice/chat/v2): ASR→Agent→TTS 正确链路
"""

import base64
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
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


class VoiceChatResponse(BaseModel):
    session_id: str
    text: str
    audio_url: str
    audio_format: str = "wav"
    voice: str = "Cherry"
    tokens_input: int = 0
    tokens_output: int = 0
    latency_ms: int = 0
    fallback: bool = False
    fallback_reason: str = ""
    # V2 Agent 完整数据
    transcribed_text: str = ""
    products: list = []
    decision_results: list = []
    evidence_list: list = []
    trace_steps: list = []


@router.post("/api/voice/chat", response_model=VoiceChatResponse)
async def voice_chat(
    audio: UploadFile = File(..., description="用户录音 WAV 文件"),
    query: str = Form("", description="可选的文字补充"),
):
    """语音导购对话 — 接收音频，返回文字回复+语音播报。

    用户边说话边打字（可选），豆仔语音回复。
    """
    session_id = str(uuid.uuid4())[:12]

    # 验证音频格式
    if audio.content_type and audio.content_type not in (
        "audio/wav", "audio/wave", "audio/x-wav",
        "audio/mpeg", "audio/mp3", "audio/mp4", "audio/m4a", "audio/aac",
        "audio/x-m4a", "audio/webm", "audio/ogg",
        "application/octet-stream",  # 部分 Android 上传无明确 MIME
    ):
        raise HTTPException(422, f"Unsupported audio format: {audio.content_type}")

    # 保存用户录音
    audio_ext = _get_ext(audio)
    user_audio_name = f"user-{session_id}.{audio_ext}"
    user_audio_path = _VOICE_DIR / user_audio_name
    audio_bytes = await audio.read()

    if len(audio_bytes) < 100:
        raise HTTPException(422, "Audio too short — please record at least 1 second")

    user_audio_path.write_bytes(audio_bytes)
    logger.info(f"Voice input saved: {user_audio_name} ({len(audio_bytes)} bytes)")

    # 调用 Qwen-Omni
    try:
        omni = _get_omni()
        prompt = query or "请分析这段语音，帮我推荐合适的商品"
        result = omni.chat_with_audio(
            audio_bytes=audio_bytes,
            text=prompt,
        )
    except Exception as e:
        logger.error(f"Qwen-Omni failed: {e}")
        return VoiceChatResponse(
            session_id=session_id,
            text="抱歉，语音服务暂时不可用，请用文字告诉我你想买什么~",
            audio_url="",
            fallback=True,
            fallback_reason=str(e)[:200],
        )

    # 保存语音回复
    resp_audio_url = ""
    if result["audio_base64"]:
        resp_audio_name = f"reply-{session_id}.wav"
        resp_audio_path = _VOICE_DIR / resp_audio_name
        try:
            audio_wav = base64.b64decode(result["audio_base64"])
            resp_audio_path.write_bytes(audio_wav)
            resp_audio_url = f"/api/uploads/voice/{resp_audio_name}"
            logger.info(f"Voice output saved: {resp_audio_name} ({len(audio_wav)} bytes)")
        except Exception as e:
            logger.warning(f"Failed to save voice output: {e}")

    return VoiceChatResponse(
        session_id=session_id,
        text=result["text"] or "这个商品很适合你~",
        audio_url=resp_audio_url,
        audio_format=result["audio_format"],
        voice=result["voice"],
        tokens_input=result["tokens_input"],
        tokens_output=result["tokens_output"],
        latency_ms=result["latency_ms"],
    )


class TranscribeResponse(BaseModel):
    text: str
    fallback: bool = False


@router.post("/api/voice/transcribe", response_model=TranscribeResponse)
async def voice_transcribe(
    audio: UploadFile = File(..., description="用户录音"),
):
    """纯 ASR 转写 — 只转语音为文字，不跑 Agent，快速返回。

    供客户端先拿到转写文字展示在聊天框，再另行调用 /api/recommend/v2。
    """
    audio_bytes = await audio.read()
    if len(audio_bytes) < 100:
        return TranscribeResponse(text="", fallback=True)

    omni = _get_omni()
    try:
        result = omni.chat_with_audio(
            audio_bytes=audio_bytes,
            text="请把这段语音逐字转写成文字，只输出转写结果，一个字都别多。",
        )
        transcribed = _clean_transcription(result.get("text", ""))
        if transcribed and len(transcribed) >= 2:
            return TranscribeResponse(text=transcribed)
    except Exception as e:
        logger.warning(f"Transcribe failed: {e}")

    return TranscribeResponse(text="", fallback=True)


@router.post("/api/voice/chat/v2", response_model=VoiceChatResponse)
async def voice_chat_v2(
    audio: UploadFile = File(..., description="用户录音"),
    query: str = Form("", description="可选文字补充"),
):
    """语音导购 v2 — ASR 转文字 → Agent Workflow → TTS 语音回复。

    语音只是输入媒介，推荐逻辑与文字输入完全一致。
    返回：转写文字 + Agent 回答文字 + 语音 URL + 商品/证据/评分/链路
    """
    session_id = str(uuid.uuid4())[:12]
    t_start = __import__("time").perf_counter()

    # 保存音频
    audio_ext = _get_ext(audio)
    user_audio_name = f"user-{session_id}.{audio_ext}"
    audio_bytes = await audio.read()
    if len(audio_bytes) < 100:
        raise HTTPException(422, "录音太短，请至少录制 1 秒")

    (_VOICE_DIR / user_audio_name).write_bytes(audio_bytes)

    omni = _get_omni()
    transcribed = query or ""
    fallback_reason = ""

    # ---- Step 1: ASR 语音转文字 ----
    if not query:
        try:
            asr_result = omni.chat_with_audio(
                audio_bytes=audio_bytes,
                text="请把这段语音转成文字，只输出转写结果，不要多余的话。",
            )
            transcribed = _clean_transcription(asr_result.get("text", ""))
            if not transcribed or len(transcribed) < 1:
                transcribed = "帮我推荐合适的商品"
                fallback_reason = "ASR returned empty"
        except Exception as e:
            logger.warning(f"ASR failed: {e}")
            transcribed = "帮我推荐合适的商品"
            fallback_reason = f"ASR error: {str(e)[:100]}"

    logger.info(f"Voice v2 ASR: {transcribed[:80]}")

    # ---- Step 2: Agent Workflow（跟打字一模一样）----
    try:
        from app.workflow.graph import run_workflow
        wf_result = await run_workflow(
            user_query=transcribed,
            image_url=None,
            session_id=session_id,
            enable_checkpoint=False,
        )
        agent_answer = wf_result.answer or "抱歉，没有找到合适的商品"
        products = wf_result.retrieved_products or []
        decisions = wf_result.decision_results or []
        evidence = wf_result.evidence_list or []
        traces = wf_result.trace_steps or []
    except Exception as e:
        logger.error(f"Agent workflow failed: {e}")
        agent_answer = f"抱歉，系统处理你的语音请求时遇到了问题：{e}"
        products, decisions, evidence, traces = [], [], [], []
        fallback_reason += f"; Agent error: {str(e)[:100]}"

    # ---- Step 3: TTS 文字转语音 ----
    resp_audio_url = ""
    try:
        tts_result = omni.chat_with_text_only(agent_answer)
        if tts_result["audio_base64"]:
            audio_wav = base64.b64decode(tts_result["audio_base64"])
            resp_name = f"reply-{session_id}.wav"
            (_VOICE_DIR / resp_name).write_bytes(audio_wav)
            resp_audio_url = f"/api/uploads/voice/{resp_name}"
    except Exception as e:
        logger.warning(f"TTS failed: {e}")
        fallback_reason += f"; TTS error: {str(e)[:80]}"

    latency_ms = round((__import__("time").perf_counter() - t_start) * 1000)

    return VoiceChatResponse(
        session_id=session_id,
        text=agent_answer,
        audio_url=resp_audio_url,
        transcribed_text=transcribed,
        products=products,
        decision_results=decisions,
        evidence_list=evidence,
        trace_steps=traces,
        latency_ms=latency_ms,
        fallback=bool(fallback_reason),
        fallback_reason=fallback_reason,
    )


def _clean_transcription(raw: str) -> str:
    """清洗 ASR 转写结果 — 去掉 Qwen-Omni 混入的 AI 回复尾巴。

    ASR 模型有时会在转写后自行添加"好的"、"还有什么可以帮您"等废话。
    策略：找到第一个自然断句点，只取纯转写内容；检测到 AI 废话特征词立即截断。
    """
    if not raw:
        return ""
    raw = raw.strip()

    # AI 废话特征词 — 出现任何一个就截断
    ai_cut_words = [
        "如果还有其他", "如果还有别的", "有什么可以", "有什么需要",
        "随时告诉我", "随时联系", "还有什么", "请问还有什么", "还有什么问题",
        "我可以", "我能帮", "让我来", "让我帮", "我来帮", "我帮你", "帮您",
        "好的", "明白了", "收到", "了解了", "没问题", "可以的",
        "这是", "以下是", "以上是", "总结", "综上所述",
        "希望", "祝你", "欢迎", "感谢",
    ]

    # 逐句检查，找到第一条 AI 废话就截断
    sentences = raw.replace("！", "。").replace("？", "。").replace("\n", "。").split("。")
    clean_sentences = []
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        # 这句是不是 AI 废话？
        is_ai = any(w in s for w in ai_cut_words) and len(s) > 5
        if is_ai:
            break
        # 这句看起来像转写内容（有购物关键词或日常用语）
        clean_sentences.append(s)

    result = "。".join(clean_sentences).strip()
    if not result:
        # 全被截断了，返回前 30 字
        return raw[:30].strip()
    return result


def _get_ext(audio: UploadFile) -> str:
    """从 content_type 推断扩展名"""
    ct = (audio.content_type or "").lower()
    if "wav" in ct or "wave" in ct:
        return "wav"
    if "mpeg" in ct or "mp3" in ct:
        return "mp3"
    if "webm" in ct:
        return "webm"
    # fallback: 从文件名推断
    if audio.filename:
        ext = Path(audio.filename).suffix.lstrip(".")
        if ext in ("wav", "mp3", "webm", "m4a", "ogg"):
            return ext
    return "wav"
