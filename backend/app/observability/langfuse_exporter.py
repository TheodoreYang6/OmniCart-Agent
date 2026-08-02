"""可选 Langfuse 导出器（默认关闭）—— 对齐 amap 的 Langfuse LLM trace（spec §九「预留」）。

设计：默认**完全关闭**、零依赖影响。仅当 ``LANGFUSE_ENABLED=true`` 且已安装 ``langfuse``
且提供密钥时才启用；任何异常都静默降级为 no-op，绝不影响主链路。collector 在记录 span
时顺带调用 ``export``，把本地 trace 同步到 Langfuse（若启用）。
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class LangfuseExporter:
    """把 LLMSpan 导出到 Langfuse（可选、默认关闭）。"""

    def __init__(self) -> None:
        self._enabled = False
        self._client: Any = None
        if os.getenv("LANGFUSE_ENABLED", "false").lower() != "true":
            return
        try:
            from langfuse import Langfuse  # 可选依赖，未装则降级

            self._client = Langfuse()
            self._enabled = True
            logger.info("LangfuseExporter enabled")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Langfuse requested but unavailable, disabled: %s", exc)
            self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def export(self, span: Any) -> None:
        """导出一条 span（no-op 当未启用）。任何异常静默吞掉。"""
        if not self._enabled or self._client is None:
            return
        try:
            trace = self._client.trace(id=getattr(span, "trace_id", None), name="omnicart.request")
            trace.generation(
                name=getattr(span, "name", "llm"),
                model=getattr(span, "model", ""),
                input=getattr(span, "user_prompt", ""),
                output=getattr(span, "response", ""),
                metadata={
                    "capability": getattr(span, "capability", ""),
                    "status": getattr(span, "status", ""),
                    "latency_ms": getattr(span, "latency_ms", 0),
                    "tokens_input": getattr(span, "tokens_input", 0),
                    "tokens_output": getattr(span, "tokens_output", 0),
                },
            )
        except Exception:  # noqa: BLE001
            pass


_exporter: LangfuseExporter | None = None


def get_langfuse_exporter() -> LangfuseExporter:
    global _exporter
    if _exporter is None:
        _exporter = LangfuseExporter()
    return _exporter
