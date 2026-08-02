"""LLM 全链路追踪收集器 — 记录每次模型调用，持久化到本地 JSON 文件。

每次 chat / vision / embed / rerank 调用自动记录：
- 模型名、capability、provider
- 完整 prompt 和 response（截断 4000 字符防膨胀）
- token 估算（从 API response 提取 usage，不可用时用字符数/4 估算）
- 延迟（毫秒）
- 状态（success / error / mock / fallback）

存储：data/traces/ 目录，按日期分文件，自动轮转。
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import logging

logger = logging.getLogger(__name__)

_TRACES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "traces"
_MAX_PROMPT_CHARS = 4000
_MAX_RESPONSE_CHARS = 4000
_MAX_TRACES_PER_FILE = 500


@dataclass
class LLMSpan:
    span_id: str
    trace_id: str
    parent_span_id: str = ""
    name: str = ""              # qwen.chat / qwen.vision / qwen.embed / qwen.rerank
    capability: str = ""
    model: str = ""
    provider: str = "qwen"
    system_prompt: str = ""
    user_prompt: str = ""
    response: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    latency_ms: float = 0
    status: str = "success"     # success / error / mock / fallback
    error: str = ""
    mock_mode: bool = False
    timestamp: str = ""
    metadata: dict = field(default_factory=dict)

    @staticmethod
    def _truncate(s: str, max_len: int = _MAX_PROMPT_CHARS) -> str:
        return s if len(s) <= max_len else s[:max_len] + f"...[truncated {len(s) - max_len} chars]"


class TraceCollector:
    """全局单例 — 记录并查询 LLM 调用追踪"""

    def __init__(self, store_dir: Path | None = None):
        self._dir = store_dir or _TRACES_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._buffer: list[LLMSpan] = []
        self._last_flush = time.time()

    # ---- public API ----

    async def record(self, span: LLMSpan) -> None:
        """记录一条 span，缓冲写入"""
        span.timestamp = span.timestamp or datetime.now().isoformat()
        self._buffer.append(span)
        # 可选：同步到 Langfuse（默认关闭，异常静默，不影响主链路）
        try:
            from app.observability.langfuse_exporter import get_langfuse_exporter

            get_langfuse_exporter().export(span)
        except Exception:
            pass
        if len(self._buffer) >= 10 or (time.time() - self._last_flush) > 30:
            self._flush()

    async def query(
        self,
        limit: int = 50,
        name: str = "",
        status: str = "",
        since: str = "",
    ) -> list[dict]:
        """查询最近的追踪记录"""
        self._flush()
        results = []
        files = sorted(self._dir.glob("traces-*.json"), reverse=True)
        for fp in files:
            if len(results) >= limit:
                break
            try:
                batch = json.loads(fp.read_text(encoding="utf-8"))
                for span in reversed(batch):
                    if len(results) >= limit:
                        break
                    if name and span.get("name") != name:
                        continue
                    if status and span.get("status") != status:
                        continue
                    if since and span.get("timestamp", "") < since:
                        continue
                    results.append(span)
            except Exception:
                pass
        return results

    async def get_span(self, span_id: str) -> dict | None:
        """按 span_id 查找单条追踪"""
        self._flush()
        for fp in sorted(self._dir.glob("traces-*.json"), reverse=True):
            try:
                batch = json.loads(fp.read_text(encoding="utf-8"))
                for span in batch:
                    if span.get("span_id") == span_id:
                        return span
            except Exception:
                pass
        return None

    async def stats(self, hours: int = 24) -> dict:
        """聚合统计：调用次数、token、延迟、错误率"""
        self._flush()
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        total = 0
        errors = 0
        mocks = 0
        tokens_in = 0
        tokens_out = 0
        latencies = []
        by_capability: dict[str, int] = {}
        by_model: dict[str, int] = {}

        for fp in sorted(self._dir.glob("traces-*.json"), reverse=True):
            try:
                batch = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                continue
            for span in batch:
                ts = span.get("timestamp", "")
                if ts < cutoff:
                    continue
                total += 1
                if span.get("status") == "error":
                    errors += 1
                if span.get("mock_mode"):
                    mocks += 1
                tokens_in += span.get("tokens_input", 0)
                tokens_out += span.get("tokens_output", 0)
                latencies.append(span.get("latency_ms", 0))
                cap = span.get("capability", "unknown")
                by_capability[cap] = by_capability.get(cap, 0) + 1
                model = span.get("model", "unknown")
                by_model[model] = by_model.get(model, 0) + 1

        sorted_lat = sorted(latencies)
        n = len(sorted_lat)
        return {
            "window_hours": hours,
            "total_calls": total,
            "errors": errors,
            "error_rate": round(errors / max(total, 1), 4),
            "mock_calls": mocks,
            "tokens_input": tokens_in,
            "tokens_output": tokens_out,
            "tokens_total": tokens_in + tokens_out,
            "latency_avg_ms": round(sum(latencies) / max(n, 1)),
            "latency_p50_ms": sorted_lat[n // 2] if n else 0,
            "latency_p95_ms": sorted_lat[int(n * 0.95)] if n > 1 else (sorted_lat[0] if n else 0),
            "by_capability": by_capability,
            "by_model": by_model,
        }

    async def clear(self, before: str = "") -> int:
        """清除追踪数据。before 为 ISO 时间，不传则全清。"""
        self._flush()
        self._buffer.clear()
        deleted = 0
        if before:
            cutoff = before
            for fp in self._dir.glob("traces-*.json"):
                try:
                    batch = json.loads(fp.read_text(encoding="utf-8"))
                    new_batch = [s for s in batch if s.get("timestamp", "") >= cutoff]
                    removed = len(batch) - len(new_batch)
                    if removed > 0:
                        deleted += removed
                        fp.write_text(json.dumps(new_batch, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
        else:
            for fp in self._dir.glob("traces-*.json"):
                try:
                    fp.unlink()
                    deleted += 1
                except Exception:
                    pass
        return deleted

    # ---- internal ----

    def _flush(self) -> None:
        if not self._buffer:
            return
        today = datetime.now().strftime("%Y-%m-%d")
        fp = self._dir / f"traces-{today}.json"

        existing = []
        if fp.exists():
            try:
                existing = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                pass

        existing.extend(asdict(s) for s in self._buffer)
        self._buffer.clear()
        self._last_flush = time.time()

        # 单文件条数限制，超出 rollover
        if len(existing) > _MAX_TRACES_PER_FILE:
            archive = self._dir / f"traces-{today}-{int(time.time())}.json"
            fp.rename(archive)
            fp.write_text("[]", encoding="utf-8")
            logger.info(f"Trace file rotated: {archive.name}")
        else:
            fp.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


# ---- helpers ----

def _estimate_tokens_input(system: str, prompt: str) -> int:
    """粗略估算输入 token 数：中英文混合按字符数/3.5"""
    text = (system or "") + (prompt or "")
    return max(1, len(text) * 2 // 7)


def _estimate_tokens_output(response: str) -> int:
    """粗略估算输出 token 数"""
    if not response:
        return 0
    return max(1, len(response) * 2 // 7)


def _extract_usage_from_response(data: dict) -> tuple[int, int]:
    """从 DashScope API 返回值提取 usage 信息"""
    usage = data.get("usage", {})
    inp = usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0)
    out = usage.get("output_tokens", 0) or usage.get("completion_tokens", 0)
    return inp, out


# ---- 全局单例 ----

_collector: TraceCollector | None = None


def get_collector() -> TraceCollector:
    global _collector
    if _collector is None:
        _collector = TraceCollector()
    return _collector
