"""
Model Gateway — 能力名驱动的模型访问层。

业务代码只调用能力名，不写死模型名：
    gateway.get_model("visual_understanding")
    gateway.chat("chat_generation", prompt="...")

配置集中在 model_config.yaml 中统一管理。
"""

import os
import re
from pathlib import Path
from typing import Any

import yaml

from app.core.config import MOCK_MODE
from app.model_gateway.mock_model import MockChat, MockEmbedding

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

    # ---- 对外 API ----

    def get_model(self, capability: str):
        """返回一个可调用的模型实例（V1 将根据 capability 返回不同类型）"""
        return _CapabilityProxy(self, capability)

    def chat(self, capability: str, prompt: str, system: str = "") -> str:
        """同步对话 — 当前 V0 用 Mock，V1 接入真实 API"""
        cfg = self._capabilities.get(capability, {})
        if MOCK_MODE:
            return MockChat().generate(prompt, system)
        # V1: 根据 cfg 调用真实 Qwen API
        from app.model_gateway.qwen_chat import QwenChat
        chat = QwenChat(
            model=cfg.get("model", "qwen-plus"),
            temperature=cfg.get("temperature", 0.7),
            max_tokens=cfg.get("max_tokens", 2048),
        )
        return chat.generate(prompt, system)

    def embed(self, texts: list[str], capability: str = "text_embedding") -> list[list[float]]:
        """文本向量化"""
        if MOCK_MODE:
            return MockEmbedding().embed(texts)
        from app.model_gateway.qwen_embedding import QwenEmbedding
        cfg = self._capabilities.get(capability, {})
        emb = QwenEmbedding(
            model=cfg.get("model", "qwen3-embedding"),
            dimensions=cfg.get("dimensions", 1024),
        )
        return emb.embed(texts)

    def vision(self, capability: str = "visual_understanding", image_path: str | None = None,
               image_bytes: bytes | None = None, content_type: str = "image/png",
               prompt: str = "", system: str = "") -> str:
        """视觉理解 — 解析图片（商品截图/详情页）"""
        cfg = self._capabilities.get(capability, {})
        if MOCK_MODE:
            return MockChat().generate(
                f"[Mock Vision] 请分析图片内容。prompt: {prompt}", system
            )
        from app.model_gateway.qwen_vision import QwenVision
        vis = QwenVision(
            model=cfg.get("model", "qwen-vl-plus"),
            temperature=cfg.get("temperature", 0.3),
            max_tokens=cfg.get("max_tokens", 2048),
        )
        if image_bytes:
            return vis.analyze_bytes(image_bytes, content_type, prompt, system)
        return vis.analyze(image_path or "", prompt, system)

    def rerank(self, query: str, documents: list[str],
               capability: str = "text_reranking", top_n: int = 10) -> list[dict]:
        """文本精排"""
        cfg = self._capabilities.get(capability, {})
        if MOCK_MODE:
            # Mock: 返回原始顺序
            return [{"index": i, "document": d, "relevance_score": 1.0 - i * 0.05}
                    for i, d in enumerate(documents[:top_n])]
        from app.model_gateway.qwen_reranker import QwenReranker
        ranker = QwenReranker(model=cfg.get("model", "qwen3-reranker"))
        return ranker.rerank(query, documents, top_n or 10)

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
