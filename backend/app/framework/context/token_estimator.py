"""Token 估算器（借鉴 amap ``libs/context_store/token_estimator.py`` 思路）。

优先用 tiktoken 精确估算；不可用时退化为「CJK 逐字 + 非 CJK 约 4 字符/token」的字符估算。
无强依赖：tiktoken 缺失时静默降级。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TokenEstimator(Protocol):
    def estimate(self, text: str) -> int: ...


def _is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


class CharTokenEstimator:
    """字符启发式估算：CJK 每字≈1 token，其余每约 4 字符≈1 token。"""

    def estimate(self, text: str) -> int:
        if not text:
            return 0
        cjk = sum(1 for ch in text if _is_cjk(ch))
        other = len(text) - cjk
        return cjk + max(1, other // 4) if other else cjk


class TiktokenEstimator:
    """基于 tiktoken 的精确估算（可用时）。"""

    def __init__(self, encoding: str = "cl100k_base") -> None:
        import tiktoken  # 延迟导入，缺失时由工厂降级

        self._enc = tiktoken.get_encoding(encoding)

    def estimate(self, text: str) -> int:
        if not text:
            return 0
        return len(self._enc.encode(text))


def create_token_estimator() -> TokenEstimator:
    """自动选择最佳估算器：tiktoken 可用则精确，否则字符估算。"""
    try:
        return TiktokenEstimator()
    except Exception:  # noqa: BLE001
        return CharTokenEstimator()
