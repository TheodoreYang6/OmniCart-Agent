"""净新增能力 Provider 抽象层 —— 库存 / 支付 / 物流。

对齐 ``framework/retrieval/source.py::RecallSource`` 的 ABC 风格：仅声明契约，
不含具体实现。默认 Mock 实现在 ``app.providers.tools.mocks``，接真实系统只需替换
工厂返回值即可，工具 / Agent 编排层无感。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

__all__ = ["InventoryProvider", "PaymentProvider", "LogisticsProvider"]


class InventoryProvider(ABC):
    """库存查询 Provider。"""

    name: str = ""
    priority: int = 100

    @abstractmethod
    async def check(self, product_id: str, sku_id: str | None = None) -> dict:
        """返回 ``{"in_stock": bool, "quantity": int, "eta": str, "level": str}``。

        level 取值 ``"in_stock" / "low" / "out"``，供上层文案分档。
        """
        ...


class PaymentProvider(ABC):
    """支付 Provider。"""

    name: str = ""
    priority: int = 100

    @abstractmethod
    async def pay(self, order_id: str, method: str = "mock") -> dict:
        """返回 ``{"status": "paid|failed", "txn_id": str, "error": str}``。"""
        ...


class LogisticsProvider(ABC):
    """物流追踪 Provider。"""

    name: str = ""
    priority: int = 100

    @abstractmethod
    async def track(self, order_id: str, created_at=None) -> dict:
        """返回 ``{"state": str, "nodes": list[{"name":..,"time":..,"done":bool}], "eta": str}``。"""
        ...
