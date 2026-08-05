"""PostgreSQL 购物车仓库。

提供 sync 和 async 两套接口：
- async 版本供 FastAPI 端点直接使用
- sync 版本通过 asyncio 桥接（供 checkout/agent_actions 兼容调用）
"""

import uuid
import logging
from typing import Optional

from sqlalchemy import select, update, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import get_session_sync, run_async
from app.models.cart_item import CartItemModel
from app.schemas.cart import Cart, CartItem, CartItemCreate, CartItemUpdate, DEMO_USER_ID

logger = logging.getLogger(__name__)


class PgCartRepository:
    """购物车仓库 — PostgreSQL 持久化存储。"""


    # ---- 异步实现 ----

    async def aget_cart(self, user_id: str = DEMO_USER_ID) -> Cart:
        factory = get_session_sync()
        if factory is None:
            return Cart(user_id=user_id)
        async with factory() as session:
            result = await session.execute(
                select(CartItemModel).where(CartItemModel.user_id == user_id)
            )
            rows = result.scalars().all()
            return Cart(user_id=user_id, items=[self._row_to_item(r) for r in rows])

    async def aadd_item(self, item_create: CartItemCreate, user_id: str = DEMO_USER_ID,
                        title: str = "", brand: str = "", price: float = 0.0,
                        image_url: str = "", sku_label: str = "") -> Optional[CartItem]:
        factory = get_session_sync()
        if factory is None:
            return None
        cart_item_id = str(uuid.uuid4())[:8]
        async with factory() as session:
            stmt = pg_insert(CartItemModel).values(
                cart_item_id=cart_item_id,
                user_id=user_id,
                product_id=item_create.product_id,
                sku_id=item_create.sku_id,
                sku_label=sku_label,
                title=title,
                brand=brand,
                price=price,
                image_url=image_url,
                quantity=item_create.quantity,
            )
            await session.execute(stmt)
            await session.commit()

        item = CartItem(
            cart_item_id=cart_item_id,
            user_id=user_id,
            product_id=item_create.product_id,
            sku_id=item_create.sku_id,
            sku_label=sku_label,
            title=title,
            brand=brand,
            price=price,
            image_url=image_url,
            quantity=item_create.quantity,
        )
        return item

    async def aupdate_item(self, cart_item_id: str, update_data: CartItemUpdate,
                           user_id: str = DEMO_USER_ID) -> Optional[CartItem]:
        factory = get_session_sync()
        if factory is None:
            return None
        async with factory() as session:
            row = await session.get(CartItemModel, cart_item_id)
            if row is None or row.user_id != user_id:
                return None
            if update_data.quantity is not None:
                row.quantity = max(1, update_data.quantity)
            if update_data.selected is not None:
                row.selected = update_data.selected
            await session.commit()
            await session.refresh(row)
            return self._row_to_item(row)

    async def aremove_item(self, cart_item_id: str, user_id: str = DEMO_USER_ID) -> bool:
        factory = get_session_sync()
        if factory is None:
            return False
        async with factory() as session:
            stmt = delete(CartItemModel).where(
                CartItemModel.cart_item_id == cart_item_id,
                CartItemModel.user_id == user_id,
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def abatch_remove(self, cart_item_ids: list[str], user_id: str = DEMO_USER_ID) -> int:
        """批量删除购物车项 — 单条 SQL DELETE IN，避免 N+1。"""
        if not cart_item_ids:
            return 0
        factory = get_session_sync()
        if factory is None:
            return 0
        async with factory() as session:
            stmt = delete(CartItemModel).where(
                CartItemModel.cart_item_id.in_(cart_item_ids),
                CartItemModel.user_id == user_id,
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    async def aselect_all(self, selected: bool, user_id: str = DEMO_USER_ID) -> bool:
        factory = get_session_sync()
        if factory is None:
            return False
        async with factory() as session:
            stmt = (
                update(CartItemModel)
                .where(CartItemModel.user_id == user_id)
                .values(selected=selected)
            )
            await session.execute(stmt)
            await session.commit()
        return True

    async def aclear_cart(self, user_id: str = DEMO_USER_ID) -> bool:
        factory = get_session_sync()
        if factory is None:
            return False
        async with factory() as session:
            stmt = delete(CartItemModel).where(CartItemModel.user_id == user_id)
            await session.execute(stmt)
            await session.commit()
        return True

    async def amerge_cart(self, source_user_id: str, target_user_id: str) -> int:
        """Merge a guest cart into a user cart in one transaction."""
        if not source_user_id or source_user_id == target_user_id:
            return 0
        factory = get_session_sync()
        if factory is None:
            return 0
        async with factory() as session:
            result = await session.execute(
                select(CartItemModel).where(
                    CartItemModel.user_id.in_([source_user_id, target_user_id])
                ).order_by(CartItemModel.created_at.asc())
            )
            rows = list(result.scalars().all())
            target_by_key = {
                (row.product_id, row.sku_id or ""): row
                for row in rows if row.user_id == target_user_id
            }
            merged_count = 0
            for row in (item for item in rows if item.user_id == source_user_id):
                key = (row.product_id, row.sku_id or "")
                existing = target_by_key.get(key)
                if existing:
                    existing.quantity = min(99, max(1, existing.quantity) + max(1, row.quantity))
                    existing.selected = existing.selected or row.selected
                    await session.delete(row)
                else:
                    row.user_id = target_user_id
                    row.quantity = min(99, max(1, row.quantity))
                    target_by_key[key] = row
                merged_count += 1
            await session.commit()
            return merged_count

    # ---- 同步接口 ----

    def get_cart(self, user_id: str = DEMO_USER_ID) -> Cart:
        return run_async(self.aget_cart(user_id))

    def add_item(self, item_create: CartItemCreate, user_id: str = DEMO_USER_ID,
                 title: str = "", brand: str = "", price: float = 0.0,
                 image_url: str = "", sku_label: str = "") -> Optional[CartItem]:
        return run_async(self.aadd_item(item_create, user_id, title, brand, price, image_url, sku_label))

    def update_item(self, cart_item_id: str, update_data: CartItemUpdate,
                    user_id: str = DEMO_USER_ID) -> Optional[CartItem]:
        return run_async(self.aupdate_item(cart_item_id, update_data, user_id))

    def remove_item(self, cart_item_id: str, user_id: str = DEMO_USER_ID) -> bool:
        return run_async(self.aremove_item(cart_item_id, user_id))

    def batch_remove(self, cart_item_ids: list[str], user_id: str = DEMO_USER_ID) -> int:
        return run_async(self.abatch_remove(cart_item_ids, user_id))

    def select_all(self, selected: bool, user_id: str = DEMO_USER_ID) -> bool:
        return run_async(self.aselect_all(selected, user_id))

    def clear_cart(self, user_id: str = DEMO_USER_ID) -> bool:
        return run_async(self.aclear_cart(user_id))

    def merge_cart(self, source_user_id: str, target_user_id: str) -> int:
        return run_async(self.amerge_cart(source_user_id, target_user_id))

    # ---- 内部 ----

    @staticmethod
    def _row_to_item(row: CartItemModel) -> CartItem:
        return CartItem(
            cart_item_id=row.cart_item_id,
            user_id=row.user_id,
            product_id=row.product_id,
            sku_id=row.sku_id,
            sku_label=row.sku_label or "",
            title=row.title or "",
            brand=row.brand or "",
            price=float(row.price),
            image_url=row.image_url or "",
            quantity=row.quantity,
            selected=row.selected,
        )


class MemCartRepository:
    """内存购物车仓库 — V0 降级实现（服务器重启丢失）。"""

    def __init__(self):
        self._carts: dict[str, Cart] = {}

    def _get_or_create(self, user_id: str) -> Cart:
        if user_id not in self._carts:
            self._carts[user_id] = Cart(user_id=user_id)
        return self._carts[user_id]

    def get_cart(self, user_id: str = DEMO_USER_ID) -> Cart:
        return self._get_or_create(user_id)

    def add_item(self, item_create: CartItemCreate, user_id: str = DEMO_USER_ID,
                 title: str = "", brand: str = "", price: float = 0.0,
                 image_url: str = "", sku_label: str = "") -> Optional[CartItem]:
        cart = self._get_or_create(user_id)
        item = CartItem(
            cart_item_id=str(uuid.uuid4())[:8],
            user_id=user_id,
            product_id=item_create.product_id,
            sku_id=item_create.sku_id,
            sku_label=sku_label,
            title=title,
            brand=brand,
            price=price,
            image_url=image_url,
            quantity=item_create.quantity,
        )
        cart.items.append(item)
        return item

    def update_item(self, cart_item_id: str, update_data: CartItemUpdate,
                    user_id: str = DEMO_USER_ID) -> Optional[CartItem]:
        cart = self._get_or_create(user_id)
        for item in cart.items:
            if item.cart_item_id == cart_item_id:
                if update_data.quantity is not None:
                    item.quantity = max(1, update_data.quantity)
                if update_data.selected is not None:
                    item.selected = update_data.selected
                return item
        return None

    def remove_item(self, cart_item_id: str, user_id: str = DEMO_USER_ID) -> bool:
        cart = self._get_or_create(user_id)
        prev_len = len(cart.items)
        cart.items = [i for i in cart.items if i.cart_item_id != cart_item_id]
        return len(cart.items) < prev_len

    def select_all(self, selected: bool, user_id: str = DEMO_USER_ID) -> bool:
        cart = self._get_or_create(user_id)
        for item in cart.items:
            item.selected = selected
        return True

    def clear_cart(self, user_id: str = DEMO_USER_ID) -> bool:
        self._carts[user_id] = Cart(user_id=user_id)
        return True

    def merge_cart(self, source_user_id: str, target_user_id: str) -> int:
        source = self._get_or_create(source_user_id)
        target = self._get_or_create(target_user_id)
        by_key = {(item.product_id, item.sku_id or ""): item for item in target.items}
        for item in source.items:
            key = (item.product_id, item.sku_id or "")
            if key in by_key:
                current = by_key[key]
                current.quantity = min(99, current.quantity + item.quantity)
                current.selected = current.selected or item.selected
            else:
                item.user_id = target_user_id
                item.quantity = min(99, max(1, item.quantity))
                target.items.append(item)
                by_key[key] = item
        merged = len(source.items)
        self._carts[source_user_id] = Cart(user_id=source_user_id)
        return merged


# ---- 工厂 ----

_cart_repo: PgCartRepository | MemCartRepository | None = None


def get_cart_repo() -> PgCartRepository | MemCartRepository:
    global _cart_repo
    if _cart_repo is None:
        from app.core.config import USE_POSTGRES
        if USE_POSTGRES:
            _cart_repo = PgCartRepository()
        else:
            _cart_repo = MemCartRepository()
    return _cart_repo
