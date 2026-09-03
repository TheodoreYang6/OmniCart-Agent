"""Mock 实现 —— 库存 / 支付 / 物流。

均为**确定性**推演（不引入随机），便于答辩演示与 A/B 对拍。接真实系统只需替换
下方 ``get_*_provider()`` 工厂返回值。
"""

from __future__ import annotations

import hashlib
import uuid as _uuid
from datetime import UTC, datetime, timedelta

from app.framework.tools.providers import (
    InventoryProvider,
    LogisticsProvider,
    PaymentProvider,
)

__all__ = [
    "MockInventoryProvider",
    "MockPaymentProvider",
    "MockLogisticsProvider",
    "get_inventory_provider",
    "get_payment_provider",
    "get_logistics_provider",
]


def _hash_int(text: str) -> int:
    return int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)


class MockInventoryProvider(InventoryProvider):
    """确定性伪库存：hash(product_id[+sku_id]) 分三档（缺货 / 低库存 / 有货）。"""

    name = "mock_inventory"

    async def check(self, product_id: str, sku_id: str | None = None) -> dict:
        key = product_id + (sku_id or "")
        bucket = _hash_int(key) % 100
        if bucket < 10:
            return {"in_stock": False, "quantity": 0, "eta": "", "level": "out"}
        if bucket < 30:
            qty = (bucket % 12) + 1  # 1..12
            return {"in_stock": True, "quantity": qty, "eta": "3-5天", "level": "low"}
        qty = 50 + (bucket % 150)  # 50..199
        return {"in_stock": True, "quantity": qty, "eta": "1-3天", "level": "in_stock"}


class MockPaymentProvider(PaymentProvider):
    """Mock 支付：始终成功，返回 txn_id。"""

    name = "mock_payment"

    async def pay(self, order_id: str, method: str = "mock") -> dict:
        return {"status": "paid", "txn_id": f"TXN-{_uuid.uuid4().hex[:8].upper()}", "error": ""}


class MockLogisticsProvider(LogisticsProvider):
    """Mock 物流：按下单时间与当前时间差推演 4 节点。"""

    name = "mock_logistics"

    _STAGES = [
        ("已揽收", timedelta(hours=1)),
        ("运输中", timedelta(hours=12)),
        ("派送中", timedelta(days=1, hours=12)),
        ("已签收", timedelta(days=2)),
    ]

    async def track(self, order_id: str, created_at=None) -> dict:
        if created_at is None:
            created_at = datetime.now(UTC)
        elif isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except Exception:  # noqa: BLE001
                created_at = datetime.now(UTC)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        elapsed = now - created_at

        nodes = []
        current_state = "待发货"
        for name, offset in self._STAGES:
            node_time = created_at + offset
            done = elapsed >= offset
            nodes.append(
                {
                    "name": name,
                    "time": node_time.strftime("%Y-%m-%d %H:%M") if done else "",
                    "done": done,
                }
            )
            if done:
                current_state = name
        # 预计送达：签收前显示剩余，签收后显示已完成
        last_done_idx = max((i for i, n in enumerate(nodes) if n["done"]), default=-1)
        if last_done_idx == len(nodes) - 1:
            eta = "已完成"
        else:
            next_offset = self._STAGES[last_done_idx + 1][1] if last_done_idx + 1 < len(self._STAGES) else timedelta()
            remaining = next_offset - elapsed
            hours = max(1, int(remaining.total_seconds() // 3600))
            eta = f"约 {hours} 小时后进入下一节点"
        return {"state": current_state, "nodes": nodes, "eta": eta}


# ---- 单例工厂（未来替换真实 provider 只改这里）----

_inv: InventoryProvider | None = None
_pay: PaymentProvider | None = None
_log: LogisticsProvider | None = None


def get_inventory_provider() -> InventoryProvider:
    global _inv
    if _inv is None:
        _inv = MockInventoryProvider()
    return _inv


def get_payment_provider() -> PaymentProvider:
    global _pay
    if _pay is None:
        _pay = MockPaymentProvider()
    return _pay


def get_logistics_provider() -> LogisticsProvider:
    global _log
    if _log is None:
        _log = MockLogisticsProvider()
    return _log
