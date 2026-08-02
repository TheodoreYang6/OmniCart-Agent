"""购物车工具族 —— 包装 ``pg_cart_repo``。

文案与 ``agent_stream.py`` 旧实现逐字对齐（保证 A/B 对拍等价）。
Phase 1 实时接入：view / remove / update_qty / clear。
``cart.add`` 已实现（单规格直加），多规格/指代解析随后续 Phase 接入实时路径。
"""

from __future__ import annotations

import logging

from app.framework.tools.protocols import Tool, ToolContext, ToolResult, ToolSpec

logger = logging.getLogger(__name__)

__all__ = [
    "ViewCartTool",
    "RemoveFromCartTool",
    "UpdateCartQtyTool",
    "ClearCartTool",
    "AddToCartTool",
]


class ViewCartTool(Tool):
    spec = ToolSpec(
        name="cart.view", category="cart", permission="read",
        description="查看购物车当前商品列表与合计金额",
        parameters={"type": "object", "properties": {}},
    )

    async def run(self, ctx: ToolContext) -> ToolResult:
        try:
            from app.repositories.pg_cart_repo import get_cart_repo

            cart = await get_cart_repo().aget_cart(ctx.user_id)
        except Exception:  # noqa: BLE001
            return ToolResult(ok=False, message="暂时无法查看购物车，请去购物车页面查看～")
        if not cart.items:
            return ToolResult(message="🛒 购物车还是空的～去逛逛商品吧！")
        lines = ["🛒 你的购物车："]
        for idx, it in enumerate(cart.items, 1):
            b = it.brand or ""
            t = it.title[:50] if it.title else ""
            lines.append(f"  {idx}. {b} {t} x{it.quantity}  ¥{it.price * it.quantity:.0f}")
        lines.append(f"\n💰 合计 ¥{cart.total_price:.0f}（{cart.total_count}件）")
        lines.append("可以对我说「删除第N个」「数量改成N」来管理购物车，说「下单」来结算～")
        return ToolResult(message="\n".join(lines), data={"count": len(cart.items)})


class RemoveFromCartTool(Tool):
    spec = ToolSpec(
        name="cart.remove", category="cart", permission="write",
        description="删除购物车中第N个商品",
        parameters={
            "type": "object",
            "properties": {"ordinal": {"type": "integer", "description": "第几个，从1开始"}},
            "required": ["ordinal"],
        },
    )

    async def run(self, ctx: ToolContext, ordinal: int | None = None) -> ToolResult:
        if ordinal is None:
            return ToolResult(ok=False, message="请说「删除第几个」哦～比如「删除第二个」")
        try:
            from app.repositories.pg_cart_repo import get_cart_repo

            repo = get_cart_repo()
            cart = await repo.aget_cart(ctx.user_id)
            if ordinal < 1 or ordinal > len(cart.items):
                return ToolResult(ok=False, message=f"购物车只有{len(cart.items)}件商品哦～")
            item = cart.items[ordinal - 1]
            title = (item.brand + " " + item.title)[:60] if item.title else "商品"
            await repo.aremove_item(item.cart_item_id, ctx.user_id)
            return ToolResult(message=f"🗑 已删除「{title}」", data={"removed": item.cart_item_id})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"cart.remove error: {e}")
            return ToolResult(ok=False, message="删除失败，请去购物车页面手动操作～")


class UpdateCartQtyTool(Tool):
    spec = ToolSpec(
        name="cart.update_qty", category="cart", permission="write",
        description="修改购物车中商品数量（可指定第N个，缺省为第一个）",
        parameters={
            "type": "object",
            "properties": {
                "quantity": {"type": "integer", "description": "目标数量"},
                "ordinal": {"type": "integer", "description": "第几个，从1开始，可缺省"},
            },
            "required": ["quantity"],
        },
    )

    async def run(self, ctx: ToolContext, quantity: int | None = None, ordinal: int | None = None) -> ToolResult:
        if quantity is None or quantity < 1:
            return ToolResult(ok=False, message="请说「数量改成N」哦～比如「数量改成2」")
        try:
            from app.repositories.pg_cart_repo import get_cart_repo
            from app.schemas.cart import CartItemUpdate

            repo = get_cart_repo()
            cart = await repo.aget_cart(ctx.user_id)
            if not cart.items:
                return ToolResult(ok=False, message="购物车还是空的～")
            if ordinal is not None:
                if ordinal < 1 or ordinal > len(cart.items):
                    return ToolResult(ok=False, message=f"购物车只有{len(cart.items)}件商品哦～")
                item = cart.items[ordinal - 1]
            else:
                item = cart.items[0]
            title = (item.brand + " " + item.title)[:60] if item.title else "商品"
            await repo.aupdate_item(item.cart_item_id, CartItemUpdate(quantity=quantity), ctx.user_id)
            return ToolResult(message=f"🔢 「{title}」数量已改为 {quantity}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"cart.update_qty error: {e}")
            return ToolResult(ok=False, message="修改失败，请去购物车页面手动操作～")


class ClearCartTool(Tool):
    spec = ToolSpec(
        name="cart.clear", category="cart", permission="write",
        description="清空购物车",
        parameters={"type": "object", "properties": {}},
    )

    async def run(self, ctx: ToolContext) -> ToolResult:
        try:
            from app.repositories.pg_cart_repo import get_cart_repo

            await get_cart_repo().aclear_cart(ctx.user_id)
            return ToolResult(message="✅ 购物车已清空～")
        except Exception:  # noqa: BLE001
            return ToolResult(ok=False, message="清空失败，请去购物车页面手动操作～")


class AddToCartTool(Tool):
    """加购工具（纯函数）。

    - sku_id 未提供(None) 且多规格 -> 返回 sku_option + data.needs_sku 信号（由编排层写 pending）；
    - sku_id="" -> 显式无规格直加；sku_id="SKUx" -> 指定规格；单规格 -> 直加。
    可选 title/brand/price 覆盖展示名与价格（来自 focus/last 引用解析），缺省用商品自身。
    """

    spec = ToolSpec(
        name="cart.add", category="cart", permission="write",
        description="将指定商品加入购物车（需要 shopping.search 返回的真实 product_id；多规格未选时返回规格选项）",
        llm_exposed=True,  # Phase 7: ReAct 多轮中 LLM 从 search 结果携带 product_id（B1 单轮时代无上下文故关闭）
        parameters={
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "sku_id": {"type": "string"},
                "quantity": {"type": "integer", "default": 1},
                "title": {"type": "string"},
                "brand": {"type": "string"},
                "price": {"type": "number"},
            },
            "required": ["product_id"],
        },
    )

    async def run(self, ctx: ToolContext, product_id: str = "", sku_id: str | None = None,
                  quantity: int = 1, title: str | None = None, brand: str | None = None,
                  price: float | None = None) -> ToolResult:
        if not product_id:
            return ToolResult(ok=False, message="请先说你想买什么，我再帮你加购哦～")
        try:
            from app.repositories.pg_cart_repo import get_cart_repo
            from app.repositories.product_repo import get_product_repo
            from app.schemas.cart import CartItemCreate

            prod_repo = get_product_repo()
            product = prod_repo.get_by_id(product_id)
            if not product:
                return ToolResult(ok=False, message="找不到这件商品了～")
            disp_title = title if title is not None else product.title
            disp_brand = brand if brand is not None else product.brand
            hint_price = price if price is not None else product.base_price
            skus = getattr(product, "skus", None) or []

            # 多规格且未提供 sku_id(None) -> 返回规格选项 + needs_sku 信号（编排层写 pending）
            if len(skus) > 1 and sku_id is None:
                sku_actions = []
                base = product.base_price or 0
                for s in skus:
                    props = s.properties or {}
                    label = " · ".join(f"{k}:{v}" for k, v in props.items())
                    sp = s.price if s.price and s.price > 0 else base
                    label += f" ¥{sp:.0f}"
                    sku_actions.append({"type": "sku_option", "label": label,
                                        "sku_id": s.sku_id, "product_id": product_id})
                sku_actions.append({"type": "sku_option", "label": "默认规格",
                                    "sku_id": "", "product_id": product_id})
                t = (disp_brand + " " + disp_title)[:50]
                return ToolResult(
                    message=f"「{t}」有 {len(skus)} 个规格，选哪个？",
                    actions=sku_actions,
                    data={"needs_sku": {"product_id": product_id, "title": disp_title,
                                        "brand": disp_brand, "base_price": hint_price}},
                )

            # 指定/单规格/无规格 -> 直接加购
            sel = None
            if sku_id:  # 非空字符串 -> 指定规格
                sel = next((s for s in skus if s.sku_id == sku_id), None)
            elif sku_id is None and skus:  # 未提供 + 单规格 -> 取第一个
                sel = skus[0]
            # sku_id == "" -> sel 保持 None（显式无规格）
            sku_label = " · ".join(f"{k}:{v}" for k, v in (sel.properties or {}).items()) if sel else ""
            add_price = sel.price if sel and sel.price > 0 else hint_price
            await get_cart_repo().aadd_item(
                CartItemCreate(product_id=product_id, sku_id=(sel.sku_id if sel else None), quantity=quantity),
                ctx.user_id,
                title=disp_title, brand=disp_brand, price=add_price,
                image_url=prod_repo.resolve_image_url(product_id), sku_label=sku_label,
            )
            t = (disp_brand + " " + disp_title)[:60]
            extra = f"（{sku_label}）" if sku_label else ""
            return ToolResult(message=f"✅ 已把「{t}」{extra}加入购物车～")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"cart.add error: {e}")
            return ToolResult(ok=False, message="加购失败，请去商品页面手动操作～")
