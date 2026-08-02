"""分级上下文压缩选择器（借鉴 amap ``context_compaction`` 的 TierSelector）。

按 ``usage_ratio = tokens / budget`` 把压缩强度分为四级 + 硬截断：

- ``L0``  ratio < l1_enter        —— 不压缩，原文保留。
- ``L1``  [l1_enter, l2_enter)    —— 轻量裁剪（工具/证据结果裁剪）。
- ``L2``  [l2_enter, l3_enter)    —— 增量摘要（保留要点）。
- ``L3``  [l3_enter, 1.0)         —— 全量摘要（激进压缩）。
- ``TRUNCATION`` ratio >= 1.0     —— 硬截断兜底。

``context_compressor`` 用它决定对话摘要的压缩档位；纯逻辑、可单测。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.framework.context.token_estimator import TokenEstimator, create_token_estimator


class Tier(str, Enum):
    """压缩层级。"""

    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    TRUNCATION = "TRUNCATION"


@dataclass
class TierThresholds:
    """各级进入阈值（usage_ratio）。"""

    l1_enter: float = 0.6
    l2_enter: float = 0.75
    l3_enter: float = 0.9


class TierSelector:
    """按 token 用量比例选择压缩层级。"""

    def __init__(
        self,
        *,
        token_budget: int,
        thresholds: TierThresholds | None = None,
        estimator: TokenEstimator | None = None,
    ) -> None:
        if token_budget <= 0:
            raise ValueError("token_budget must be positive")
        self._budget = token_budget
        self._thresholds = thresholds or TierThresholds()
        self._estimator = estimator or create_token_estimator()

    def usage_ratio(self, text: str) -> float:
        return self._estimator.estimate(text) / self._budget

    def select(self, text: str) -> Tier:
        return self.select_by_ratio(self.usage_ratio(text))

    def select_by_ratio(self, ratio: float) -> Tier:
        t = self._thresholds
        if ratio >= 1.0:
            return Tier.TRUNCATION
        if ratio >= t.l3_enter:
            return Tier.L3
        if ratio >= t.l2_enter:
            return Tier.L2
        if ratio >= t.l1_enter:
            return Tier.L1
        return Tier.L0
