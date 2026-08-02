"""订单仓库 —— PG（生产）+ 内存（测试/无 PG 场景）。

对齐 ``pg_cart_repo.py`` 风格：仅异步接口。承载 ``order.list/detail/cancel/pay/track``
所需读写操作，替代此前散落在 checkout.py / agent_stream / order.submit 的内联 SQL。
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.core.database import get_session_sync
from app.models.order import OrderModel

logger = logging.getLogger(__name__)


class PgOrderRepository:
    """PostgreSQL 订单仓库（生产）。"""

    async def alist_by_user(self, user_id: str, limit: int = 20) -> list[dict]:
        factory = get_session_sync()
        if factory is None:
            return []
        try:
            async with factory() as session:
                result = await session.execute(
                    select(OrderModel)
                    .where(OrderModel.user_id == user_id)
                    .order_by(OrderModel.created_at.desc())
                    .limit(limit)
                )
                return [r.to_dict() for r in result.scalars().all()]
        except Exception as e:  # noqa: BLE001
            logger.warning(f"alist_by_user failed for {user_id}: {e}")
            return []

    async def aget(self, order_id: str) -> dict | None:
        factory = get_session_sync()
        if factory is None:
            return None
        try:
            async with factory() as session:
                row = await session.get(OrderModel, order_id)
                return row.to_dict() if row else None
        except Exception as e:  # noqa: BLE001
            logger.warning(f"aget failed for {order_id}: {e}")
            return None

    async def aupdate_status(self, order_id: str, status: str) -> bool:
        factory = get_session_sync()
        if factory is None:
            return False
        try:
            async with factory() as session:
                row = await session.get(OrderModel, order_id)
                if not row:
                    return False
                row.status = status
                await session.commit()
                return True
        except Exception as e:  # noqa: BLE001
            logger.warning(f"aupdate_status failed for {order_id}: {e}")
            return False


class MemOrderRepository:
    """内存订单仓库 —— 测试与无 PG 场景（服务器重启丢失）。"""

    def __init__(self):
        self._orders: dict[str, dict] = {}

    def seed(self, orders: list[dict]) -> None:
        for o in orders:
            oid = o.get("order_id", "")
            if oid:
                self._orders[oid] = dict(o)

    async def alist_by_user(self, user_id: str, limit: int = 20) -> list[dict]:
        items = [o for o in self._orders.values() if o.get("user_id") == user_id]
        # 按 created_at 倒序（字符串比较即可，ISO 格式）
        items.sort(key=lambda o: o.get("created_at", ""), reverse=True)
        return items[:limit]

    async def aget(self, order_id: str) -> dict | None:
        o = self._orders.get(order_id)
        return dict(o) if o else None

    async def aupdate_status(self, order_id: str, status: str) -> bool:
        if order_id not in self._orders:
            return False
        self._orders[order_id]["status"] = status
        return True


# ---- 工厂 ----

_order_repo: PgOrderRepository | MemOrderRepository | None = None


def get_order_repo() -> PgOrderRepository | MemOrderRepository:
    global _order_repo
    if _order_repo is None:
        from app.core.config import USE_POSTGRES

        _order_repo = PgOrderRepository() if USE_POSTGRES else MemOrderRepository()
    return _order_repo
