"""
Model Gateway — 能力名驱动的模型访问层。

业务代码只调用能力名，不写死模型名：
    gateway.get_model("visual_understanding")
    gateway.chat("chat_generation", prompt="...")

配置集中在 model_config.yaml 中统一管理。

每次 LLM 调用自动记录到 TraceCollector（可观测性）。
"""

import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

import yaml

from app.core.config import MOCK_MODE
from app.model_gateway.mock_model import MockChat, MockEmbedding
from app.observability.collector import (
    get_collector, LLMSpan,
    _estimate_tokens_input, _estimate_tokens_output, _extract_usage_from_response,
)

_log = __import__("logging").getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent / "model_config.yaml"


def _subst_env(value: Any) -> Any:
    """递归替换 ${ENV_VAR} 占位符为环境变量值"""
    if isinstance(value, str):
        def _repl(m):
            return os.getenv(m.group(1), "")
        return re.sub(r"\$\{(\w+)\}", _repl, value)
    if isinstance(value, dict):
        return {k: _subst_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_subst_env(v) for v in value]
    return value


class ModelGateway:
    def __init__(self, config_path: Path | None = None):
        raw = yaml.safe_load((config_path or _CONFIG_PATH).read_text(encoding="utf-8"))
        self._config = _subst_env(raw)
        self._capabilities: dict[str, dict] = self._config.get("capabilities", {})

    # ---- Trace Helper ----

    async def _trace(self, name: str, capability: str, model: str,
                     system: str, prompt: str, response: str,
                     t0: float, status: str, error: str = "",
                     api_usage: dict | None = None) -> None:
        """异步记录一条 LLM 调用追踪"""
        try:
            inp_tokens, out_tokens = 0, 0
            if api_usage:
                inp_tokens = api_usage.get("input_tokens", 0)
                out_tokens = api_usage.get("output_tokens", 0)
            if not inp_tokens:
                inp_tokens = _estimate_tokens_input(system, prompt)
            if not out_tokens and response:
                out_tokens = _estimate_tokens_output(response)

            span = LLMSpan(
                span_id=str(uuid.uuid4())[:12],
                trace_id=str(uuid.uuid4())[:12],
                name=name,
                capability=capability,
                model=model,
                provider="qwen",
                system_prompt=LLMSpan._truncate(system),
                user_prompt=LLMSpan._truncate(prompt),
                response=LLMSpan._truncate(response),
                tokens_input=inp_tokens,
                tokens_output=out_tokens,
                latency_ms=round((time.perf_counter() - t0) * 1000),
                status=status,
                error=error,
                mock_mode=MOCK_MODE,
            )
            await get_collector().record(span)
        except Exception:
            pass  # 追踪失败不影响业务

    # ---- 对外 API ----

    def get_model(self, capability: str):
        """返回一个可调用的模型实例（V1 将根据 capability 返回不同类型）"""
        return _CapabilityProxy(self, capability)

    async def chat(self, capability: str, prompt: str, system: str = "") -> str:
        """对话生成 — 自动追踪"""
        cfg = self._capabilities.get(capability, {})
        model = cfg.get("model", "qwen-plus")
        t0 = time.perf_counter()
        status, error, response = "success", "", ""
        try:
            if MOCK_MODE:
                response = MockChat().generate(prompt, system)
                status = "mock"
            else:
                from app.model_gateway.qwen_chat import QwenChat
                chat = QwenChat(
                    model=model,
                    temperature=cfg.get("temperature", 0.7),
                    max_tokens=cfg.get("max_tokens", 2048),
                )
                response = chat.generate(prompt, system)
        except Exception as e:
            status, error = "error", str(e)[:500]
        await self._trace("qwen.chat", capability, model, system, prompt, response,
                          t0, status, error)
        if status == "error":
            raise RuntimeError(error)
        return response

    async def embed(self, texts: list[str], capability: str = "text_embedding") -> list[list[float]]:
        """文本向量化 — 自动追踪"""
        cfg = self._capabilities.get(capability, {})
        model = cfg.get("model", "qwen3-embedding")
        t0 = time.perf_counter()
        status, error, result = "success", "", []
        prompt_snippet = texts[0][:200] if texts else ""
        try:
            if MOCK_MODE:
                result = MockEmbedding().embed(texts)
                status = "mock"
            else:
                from app.model_gateway.qwen_embedding import QwenEmbedding
                emb = QwenEmbedding(
                    model=model,
                    dimensions=cfg.get("dimensions", 1024),
                )
                result = emb.embed(texts)
        except Exception as e:
            status, error = "error", str(e)[:500]
        await self._trace("qwen.embed", capability, model, "", prompt_snippet,
                          f"{len(texts)} vectors, {len(result[0]) if result else 0}d",
                          t0, status, error)
        if status == "error":
            raise RuntimeError(error)
        return result

    async def vision(self, capability: str = "visual_understanding", image_path: str | None = None,
                     image_bytes: bytes | None = None, content_type: str = "image/png",
                     prompt: str = "", system: str = "") -> str:
        """视觉理解 — 自动追踪"""
        cfg = self._capabilities.get(capability, {})
        model = cfg.get("model", "qwen-vl-plus")
        t0 = time.perf_counter()
        status, error, response = "success", "", ""
        image_info = image_path or f"bytes:{len(image_bytes) if image_bytes else 0}"
        try:
            if MOCK_MODE:
                response = MockChat().generate(
                    f"[Mock Vision] image={image_info}. prompt: {prompt}", system
                )
                status = "mock"
            else:
                from app.model_gateway.qwen_vision import QwenVision
                vis = QwenVision(
                    model=model,
                    temperature=cfg.get("temperature", 0.3),
                    max_tokens=cfg.get("max_tokens", 2048),
                )
                if image_bytes:
                    response = vis.analyze_bytes(image_bytes, content_type, prompt, system)
                else:
                    response = vis.analyze(image_path or "", prompt, system)
        except Exception as e:
            status, error = "error", str(e)[:500]
        await self._trace("qwen.vision", capability, model, system, prompt, response,
                          t0, status, error)
        if status == "error":
            raise RuntimeError(error)
        return response

    async def rerank(self, query: str, documents: list[str],
                     capability: str = "text_reranking", top_n: int = 10) -> list[dict]:
        """文本精排 — 自动追踪"""
        cfg = self._capabilities.get(capability, {})
        model = cfg.get("model", "qwen3-reranker")
        t0 = time.perf_counter()
        status, error, result = "success", "", []
        prompt_snippet = f"query={query[:200]}, docs={len(documents)}"
        try:
            if MOCK_MODE:
                result = [{"index": i, "document": d, "relevance_score": 1.0 - i * 0.05}
                          for i, d in enumerate(documents[:top_n])]
                status = "mock"
            else:
                from app.model_gateway.qwen_reranker import QwenReranker
                ranker = QwenReranker(model=model)
                result = ranker.rerank(query, documents, top_n or 10)
        except Exception as e:
            status, error = "error", str(e)[:500]
        await self._trace("qwen.rerank", capability, model, "", prompt_snippet,
                          f"{len(result)} results", t0, status, error)
        if status == "error":
            raise RuntimeError(error)
        return result

    def get_capability_config(self, capability: str) -> dict:
        """读取某个能力的配置（模型名、温度等）"""
        return dict(self._capabilities.get(capability, {}))

    def list_capabilities(self) -> list[str]:
        return list(self._capabilities.keys())

    @property
    def mock_mode(self) -> bool:
        return MOCK_MODE


class _CapabilityProxy:
    """轻量代理，方便链式调用"""
    def __init__(self, gateway: ModelGateway, capability: str):
        self._gw = gateway
        self._cap = capability

    def chat(self, prompt: str, system: str = "") -> str:
        return self._gw.chat(self._cap, prompt, system)

    @property
    def config(self) -> dict:
        return self._gw.get_capability_config(self._cap)


_model_gateway: ModelGateway | None = None


def get_model_gateway() -> ModelGateway:
    global _model_gateway
    if _model_gateway is None:
        _model_gateway = ModelGateway()
    return _model_gateway
