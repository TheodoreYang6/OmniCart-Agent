"""召回源抽象基类（借鉴 amap ``libs/knowledge_base/source.py`` 的 RetrievalSource）。

每个召回源封装一类检索/证据挖掘逻辑；框架层编排器只负责调度、超时、熔断、融合，
不感知源内部实现。源通过 ``stage`` 声明其在管线中的阶段，复现现 retrieval_agent
的三段式流程：

- ``RECALL``：主召回，产出商品（+ 自带证据）。多源并行。
- ``FALLBACK``：兜底召回，仅当主召回商品数 < ``query.min_results`` 时触发
  （对齐现 ``_supplementary_evidence_search`` 的 ``< 3`` 逻辑）。
- ``ENRICH``：证据增强，读取 ``query.seed_products`` 二次挖掘证据（review/policy）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.framework.retrieval.types import RetrievalQuery, RetrievalResult

# 管线阶段常量
STAGE_RECALL = "recall"
STAGE_FALLBACK = "fallback"
STAGE_ENRICH = "enrich"


class RecallSource(ABC):
    """召回源抽象基类。

    Attributes:
        name: 唯一标识（snake_case，同类唯一）。
        priority: 优先级，越小越靠前（影响商品拼接顺序）。
        latency_budget_ms: 单源 SLA 超时（毫秒），超时即熔断降级。
        is_required: 是否必需。必需源失败时整体检索上抛异常；非必需源静默降级。
        stage: 所属阶段（recall / fallback / enrich）。
    """

    name: str = ""
    priority: int = 100
    latency_budget_ms: int = 3000
    is_required: bool = False
    stage: str = STAGE_RECALL

    @abstractmethod
    async def search(self, query: RetrievalQuery) -> RetrievalResult:
        """执行检索/证据挖掘。子类实现具体逻辑。"""
        ...

    def should_activate(self, query: RetrievalQuery) -> bool:
        """条件激活。默认恒真；子类可按 query 决定是否参与本次检索。"""
        return True
