"""OmniCart Prompt 管理包 — 所有 LLM Prompt 模板的唯一入口。

设计模仿 amap-ai-agent 的 prompt 管理模式（commons/*/prompts.py）：
- Prompt 模板与业务逻辑分离，按层级分文件集中管理
- 业务代码只通过 build_xxx() / get_xxx() 函数获取渲染后的 prompt
- 模板常量（大写命名）可直接 import 用于测试和审计

目录结构：
- agent_prompts.py    Router / Response Agent（意图路由、闲聊、推荐回答）
- service_prompts.py  对话摘要 / 偏好解析 / 关键词改写
- api_prompts.py      对话标题生成 / 商品聚焦分析
- gateway_prompts.py  语音 ASR / TTS 系统提示词
- eval_prompts.py     RAG 评测 LLM-as-Judge
"""

from app.prompts.agent_prompts import (
    CHITCHAT_PROMPT,
    RESPONSE_PROMPT,
    ROUTER_PROMPT,
    build_chitchat_prompt,
    build_response_prompt,
    build_router_prompt,
)
from app.prompts.api_prompts import (
    FOCUSED_ANALYSIS_CAT_ANGLES,
    FOCUSED_ANALYSIS_PROMPT,
    TITLE_GENERATION_PROMPT,
    build_focused_analysis_prompt,
    build_title_prompt,
    get_analysis_angle,
)
from app.prompts.eval_prompts import (
    CONTEXT_PRECISION_SYSTEM,
    CONTEXT_RECALL_SYSTEM,
    FAITHFULNESS_SYSTEM,
    build_context_precision_user,
    build_context_recall_user,
    build_faithfulness_user,
)
from app.prompts.gateway_prompts import (
    ASR_TRANSCRIBE_PROMPT,
    TTS_SYSTEM,
    VOICE_RECOMMEND_SYSTEM,
    get_asr_transcribe_prompt,
    get_tts_system,
    get_tts_system_fallback,
    get_voice_recommend_system,
    get_voice_recommend_user_prompt,
)
from app.prompts.service_prompts import (
    COMPRESSION_SYSTEM,
    COMPRESSION_USER,
    KEYWORD_EXTRACT_PROMPT,
    PROFILE_PARSE_SYSTEM,
    build_compression_user,
    build_keyword_extract_prompt,
    build_profile_parse_user,
    get_compression_system,
    get_profile_parse_system,
)

__all__ = [
    # agent
    "ROUTER_PROMPT", "CHITCHAT_PROMPT", "RESPONSE_PROMPT",
    "build_router_prompt", "build_chitchat_prompt", "build_response_prompt",
    # service
    "COMPRESSION_SYSTEM", "COMPRESSION_USER", "PROFILE_PARSE_SYSTEM", "KEYWORD_EXTRACT_PROMPT",
    "get_compression_system", "build_compression_user",
    "get_profile_parse_system", "build_profile_parse_user",
    "build_keyword_extract_prompt",
    # api
    "TITLE_GENERATION_PROMPT", "FOCUSED_ANALYSIS_PROMPT", "FOCUSED_ANALYSIS_CAT_ANGLES",
    "build_title_prompt", "build_focused_analysis_prompt", "get_analysis_angle",
    # gateway
    "ASR_TRANSCRIBE_PROMPT", "VOICE_RECOMMEND_SYSTEM", "TTS_SYSTEM",
    "get_asr_transcribe_prompt", "get_voice_recommend_user_prompt",
    "get_voice_recommend_system", "get_tts_system", "get_tts_system_fallback",
    # eval
    "FAITHFULNESS_SYSTEM", "CONTEXT_PRECISION_SYSTEM", "CONTEXT_RECALL_SYSTEM",
    "build_faithfulness_user", "build_context_precision_user", "build_context_recall_user",
]
