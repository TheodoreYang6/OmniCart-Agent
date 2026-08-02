"""
Model Gateway — 能力名驱动的模型访问层。

业务代码只调用能力名，不写死模型名：
    gateway.get_model("visual_understanding")
    gateway.chat("chat_generation", prompt="...")

配置集中在 model_config.yaml 中统一管理。

每次 LLM 调用自动记录到 TraceCollector（可观测性）+ 终端审计日志。
"""

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

import yaml

from app.core.config import MOCK_MODE
from app.model_gateway.providers import get_provider
from app.observability.request_context import get_trace_id
from app.observability.collector import (
    get_collector, LLMSpan,
    _estimate_tokens_input, _estimate_tokens_output,
)

_log = __import__("logging").getLogger(__name__)

# 审计日志 — 每次模型调用终端可见
_audit = __import__("logging").getLogger("omnicart.audit")
_audit.setLevel(__import__("logging").INFO)
if not _audit.handlers:
    _h = __import__("logging").StreamHandler()
    _h.setFormatter(__import__("logging").Formatter("%(message)s"))
    _audit.addHandler(_h)
    _audit.propagate = False


def _audit_call(capability: str, model: str, prompt: str, response: str, latency_ms: int, status: str):
    """终端输出每次模型调用摘要。"""
    p = (prompt or "").replace("\n", "\\n")[:200]
    r = (response or "").replace("\n", "\\n")[:150]
    tag = "✅" if status == "success" else "❌"
    _audit.info(f"{tag} [{capability}] {model} | {latency_ms}ms | in: {p}...")
    if r:
        _audit.info(f"   out: {r}...")
    _audit.info("")

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
                     api_usage: dict | None = None, provider_label: str = "qwen") -> None:
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
                trace_id=get_trace_id() or str(uuid.uuid4())[:12],
                name=name,
                capability=capability,
                model=model,
                provider=provider_label,
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
            provider = get_provider(MOCK_MODE)
            response = await provider.chat(
                model=model,
                prompt=prompt,
                system=system,
                temperature=cfg.get("temperature", 0.7),
                max_tokens=cfg.get("max_tokens", 2048),
            )
            if provider.is_mock:
                status = "mock"
        except Exception as e:
            status, error = "error", str(e)[:500]
        await self._trace("qwen.chat", capability, model, system, prompt, response,
                          t0, status, error)
        _audit_call(capability, model, system + " " + prompt, response, round((time.perf_counter() - t0) * 1000), status)
        if status == "error":
            raise RuntimeError(error)
        return response

    async def chat_with_tools(self, capability: str, messages: list[dict],
                              tools: list[dict], system: str = "") -> dict:
        """OpenAI function-calling — 自动追踪。

        provider 缺 chat_with_tools（如 local 后端）或异常时返空结果，
        调用方（ToolDispatcher）按 no_match 降级，不阻断主链。
        """
        cfg = self._capabilities.get(capability, {})
        model = cfg.get("model", "qwen3.7-flash-2026-07-15")
        t0 = time.perf_counter()
        status, error = "success", ""
        result: dict = {"content": "", "tool_calls": []}
        prompt_snippet = (messages[-1].get("content", "") if messages else "")[:500]
        try:
            provider = get_provider(MOCK_MODE)
            fn = getattr(provider, "chat_with_tools", None)
            if fn is None:
                status = "skipped"  # local 后端未实现 → 降级空结果
            else:
                result = await fn(
                    model=model, messages=messages, tools=tools, system=system,
                    temperature=cfg.get("temperature", 0.1),
                    max_tokens=cfg.get("max_tokens", 512),
                )
                if provider.is_mock:
                    status = "mock"
        except Exception as e:  # noqa: BLE001 — 工具选择失败不阻断主链
            status, error = "error", str(e)[:500]
        resp_summary = json.dumps(result.get("tool_calls", []), ensure_ascii=False)[:500]
        await self._trace("qwen.chat_tools", capability, model, system, prompt_snippet,
                          resp_summary, t0, status, error)
        _audit_call(capability, model, system + " " + prompt_snippet, resp_summary,
                    round((time.perf_counter() - t0) * 1000), status)
        if status == "error":
            raise RuntimeError(error)
        return result

    async def chat_stream(self, capability: str, prompt: str, system: str = ""):
        """流式对话生成 — 每个 token yield"""
        cfg = self._capabilities.get(capability, {})
        model = cfg.get("model", "qwen-plus")
        t0 = time.perf_counter()
        full_response = ""
        try:
            provider = get_provider(MOCK_MODE)
            async for token in provider.chat_stream(
                model=model,
                prompt=prompt,
                system=system,
                temperature=cfg.get("temperature", 0.7),
                max_tokens=cfg.get("max_tokens", 2048),
            ):
                full_response += token
                yield token
            status = "mock" if provider.is_mock else "success"
        except Exception as e:
            status, error = "error", str(e)[:500]
            _audit_call(capability, model, system + " " + prompt, "", round((time.perf_counter() - t0) * 1000), status)
            raise RuntimeError(error) from e
        _audit_call(capability, model, system + " " + prompt, full_response, round((time.perf_counter() - t0) * 1000), status)

    async def embed(self, texts: list[str], capability: str = "text_embedding",
                    is_query: bool = False) -> list[list[float]]:
        """文本向量化 — 自动追踪。

        is_query=True 时启用非对称编码查询侧（Qwen3-Embedding 官方用法：
        本地模型加 instruct 前缀 / API 传 text_type=query）；文档索引侧保持默认 False。
        """
        cfg = self._capabilities.get(capability, {})
        model = cfg.get("model", "qwen3-embedding")
        t0 = time.perf_counter()
        status, error, result = "success", "", []
        prompt_snippet = texts[0][:200] if texts else ""
        disp_model, plabel = model, "qwen"
        try:
            provider = get_provider(MOCK_MODE)
            plabel = "mock" if provider.is_mock else getattr(provider, "name", "qwen")
            if plabel == "local":
                disp_model = getattr(provider, "embed_model", model)
            result = await provider.embed(
                texts=texts, model=model, dimensions=cfg.get("dimensions", 1024),
                is_query=is_query,
            )
            if provider.is_mock:
                status = "mock"
        except Exception as e:
            status, error = "error", str(e)[:500]
        await self._trace("qwen.embed", capability, disp_model, "", prompt_snippet,
                          f"{len(texts)} vectors, {len(result[0]) if result else 0}d",
                          t0, status, error, provider_label=plabel)
        _audit_call(capability, disp_model, prompt_snippet, f"{len(texts)}vecs/{len(result[0]) if result else 0}d", round((time.perf_counter() - t0) * 1000), status)
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
            provider = get_provider(MOCK_MODE)
            response = await provider.vision(
                model=model,
                temperature=cfg.get("temperature", 0.3),
                max_tokens=cfg.get("max_tokens", 2048),
                prompt=prompt,
                system=system,
                image_path=image_path,
                image_bytes=image_bytes,
                content_type=content_type,
                image_info=image_info,
            )
            if provider.is_mock:
                status = "mock"
        except Exception as e:
            status, error = "error", str(e)[:500]
        await self._trace("qwen.vision", capability, model, system, prompt, response,
                          t0, status, error)
        _audit_call(capability, model, system + " " + prompt, response, round((time.perf_counter() - t0) * 1000), status)
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
        disp_model, plabel = model, "qwen"
        try:
            provider = get_provider(MOCK_MODE)
            plabel = "mock" if provider.is_mock else getattr(provider, "name", "qwen")
            if plabel == "local":
                disp_model = getattr(provider, "rerank_model", model)
            result = await provider.rerank(
                query=query, documents=documents, model=model, top_n=top_n
            )
            if provider.is_mock:
                status = "mock"
        except Exception as e:
            status, error = "error", str(e)[:500]
        await self._trace("qwen.rerank", capability, disp_model, "", prompt_snippet,
                          f"{len(result)} results", t0, status, error, provider_label=plabel)
        _audit_call(capability, disp_model, prompt_snippet, f"{len(result)} results, top={result[0]['relevance_score']:.3f}" if result else "0 results", round((time.perf_counter() - t0) * 1000), status)
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

    async def chat(self, prompt: str, system: str = "") -> str:
        return await self._gw.chat(self._cap, prompt, system)

    @property
    def config(self) -> dict:
        return self._gw.get_capability_config(self._cap)


_model_gateway: ModelGateway | None = None


def get_model_gateway() -> ModelGateway:
    global _model_gateway
    if _model_gateway is None:
        _model_gateway = ModelGateway()
    return _model_gateway
