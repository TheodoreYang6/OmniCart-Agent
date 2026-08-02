"""请求级 trace_id 传播（contextvar）。

现状：``gateway._trace`` 每个 span 各自生成随机 trace_id，无法把一次请求内的多次
LLM 调用（Router/Retrieval/Reranker/Decision/Response）串成一条链路。本模块用
contextvar 在请求入口设置一个 trace_id，``gateway._trace`` 读取它，实现同一请求的
span 共享 trace_id（对齐 amap 的全链路 trace 思路，纯标准库、无外部依赖）。
"""

from __future__ import annotations

import contextvars
import uuid

_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("omnicart_trace_id", default="")


def new_trace_id() -> str:
    return uuid.uuid4().hex[:12]


def get_trace_id() -> str:
    """返回当前请求的 trace_id（未设置返回空串）。"""
    return _trace_id.get()


def set_trace_id(trace_id: str) -> None:
    _trace_id.set(trace_id)


def ensure_trace_id(preferred: str = "") -> str:
    """确保当前上下文有 trace_id：已存在则复用，否则用 preferred（如 session_id）或新生成。"""
    current = _trace_id.get()
    if current:
        return current
    tid = preferred or new_trace_id()
    _trace_id.set(tid)
    return tid
