"""PostgreSQL 购物车仓库。

提供 sync 和 async 两套接口：
- async 版本供 FastAPI 端点直接使用
- sync 版本通过 asyncio 桥接（供 checkout/agent_actions 兼容调用）
"""

import asyncio
import uuid
import logging
from typing import Optional

import nest_asyncio
from sqlalchemy import select, update, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import get_session_sync
from app.models.cart_item import CartItemModel
from app.schemas.cart import Cart, CartItem, CartItemCreate, CartItemUpdate, DEMO_USER_ID

logger = logging.getLogger(__name__)
_nest_patched = False


class PgCartRepository:
    """购物车仓库 — PostgreSQL 持久化存储。"""

    def _run(self, coro):
        global _nest_patched
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        if not _nest_patched:
            nest_asyncio.apply(loop)
            _nest_patched = True

        return loop.run_until_complete(coro)

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
                        image_url: str = "") -> Optional[CartItem]:
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

    # ---- 同步接口 ----

    def get_cart(self, user_id: str = DEMO_USER_ID) -> Cart:
        return self._run(self.aget_cart(user_id))

    def add_item(self, item_create: CartItemCreate, user_id: str = DEMO_USER_ID,
                 title: str = "", brand: str = "", price: float = 0.0,
                 image_url: str = "") -> Optional[CartItem]:
        return self._run(self.aadd_item(item_create, user_id, title, brand, price, image_url))

    def update_item(self, cart_item_id: str, update_data: CartItemUpdate,
                    user_id: str = DEMO_USER_ID) -> Optional[CartItem]:
        return self._run(self.aupdate_item(cart_item_id, update_data, user_id))

    def remove_item(self, cart_item_id: str, user_id: str = DEMO_USER_ID) -> bool:
        return self._run(self.aremove_item(cart_item_id, user_id))

    def select_all(self, selected: bool, user_id: str = DEMO_USER_ID) -> bool:
        return self._run(self.aselect_all(selected, user_id))

    def clear_cart(self, user_id: str = DEMO_USER_ID) -> bool:
        return self._run(self.aclear_cart(user_id))

    # ---- 内部 ----

    @staticmethod
    def _row_to_item(row: CartItemModel) -> CartItem:
        return CartItem(
            cart_item_id=row.cart_item_id,
            user_id=row.user_id,
            product_id=row.product_id,
            sku_id=row.sku_id,
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
                 image_url: str = "") -> Optional[CartItem]:
        cart = self._get_or_create(user_id)
        item = CartItem(
            cart_item_id=str(uuid.uuid4())[:8],
            user_id=user_id,
            product_id=item_create.product_id,
            sku_id=item_create.sku_id,
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
