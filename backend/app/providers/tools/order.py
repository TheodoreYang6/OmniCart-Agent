"""订单工具族 —— 纯函数：预览（不落库）/ 提交（落库）。

文案与 ``agent_stream.py`` 旧实现逐字对齐（保证 A/B 对拍等价）。
引用解析 / 地址解析 / 多轮 pending 由 ShopActionAgent 编排层负责，工具只接收具体 items/address。
净新增能力（list/detail/cancel/track/pay）留 Phase 2b。
"""

from __future__ import annotations

import logging

from app.framework.tools.protocols import Tool, ToolContext, ToolResult, ToolSpec

logger = logging.getLogger(__name__)

__all__ = [
    "OrderPreviewTool",
    "OrderSubmitTool",
    "OrderListTool",
    "OrderDetailTool",
    "OrderCancelTool",
    "OrderTrackTool",
    "OrderPayTool",
]

_STATUS_CN = {"pending": "待支付", "paid": "已支付", "shipped": "已发货", "cancelled": "已取消"}

_ITEMS_SCHEMA = {"type": "array", "items": {"type": "object"}}


class OrderPreviewTool(Tool):
    """下单确认卡片（预览，不落库）。"""

    spec = ToolSpec(
        name="order.preview",
        category="order",
        permission="read",
        description="生成订单确认卡片（预览，不持久化；items 用 shopping.search/cart 返回的真实商品）",
        llm_exposed=True,  # Phase 7: LLM 可自主预览；提交/支付/取消仍需用户确认（permission=order 拦截）
        parameters={
            "type": "object",
            "properties": {"items": _ITEMS_SCHEMA, "address": {"type": "object"}},
            "required": ["items"],
        },
    )

    async def run(self, ctx: ToolContext, items: list | None = None, address: dict | None = None) -> ToolResult:
        items = items or []
        if not items:
            return ToolResult(ok=False, message="请先去浏览商品、加入购物车，或者点「问欧米」分析后再说「下单」哦～")
        from app.services.checkout_service import order_preview_card

        shop_card, message, actions, _total = order_preview_card(items, address)
        return ToolResult(
            message=message,
            actions=actions,
            data={"pending_order_items": items, "shop_card": shop_card, "needs_llm_summary": True},
        )


class OrderSubmitTool(Tool):
    """提交并持久化订单（需确认；不清空购物车，清车由编排层按来源决定）。"""

    spec = ToolSpec(
        name="order.submit",
        category="order",
        permission="order",
        description="提交并持久化订单（需 _confirmed 确认）",
        llm_exposed=False,  # 双重保险：permission=order 已被 llm_only 过滤，显式标记意图
        parameters={
            "type": "object",
            "properties": {"items": _ITEMS_SCHEMA, "address": {"type": "object"}},
            "required": ["items", "address"],
        },
    )

    async def run(self, ctx: ToolContext, items: list | None = None, address: dict | None = None) -> ToolResult:
        items = items or []
        if not items:
            return ToolResult(ok=False, message="没有找到要下单的商品～")
        from app.services.checkout_service import order_created_card, order_total, persist_order

        total = order_total(items)
        try:
            order_id = await persist_order(ctx.user_id, items, total)
        except Exception as exc:  # noqa: BLE001
            logger.error("order.submit persist failed: %s", exc, exc_info=True)
            return ToolResult(ok=False, message="订单提交失败，请稍后再试")

        shop_card, message = order_created_card(order_id, items, total)

        # Phase 3 A2A：发布 order.created 产物（registry 自动落黑板，供未来订阅方消费）
        from app.schemas.a2a import Artifact

        artifact = Artifact(
            artifact_id=f"A-{order_id}",
            artifact_type="order.created",
            producer_agent="tool:order.submit",
            content={"order_id": order_id, "total": total, "item_count": len(items)},
        )
        return ToolResult(
            message=message,
            data={"order_id": order_id, "shop_card": shop_card, "needs_llm_summary": True},
            artifacts=[artifact],
            actions=[{"type": "quick_reply", "label": "查看订单", "route": "orders"}],
        )


# ================================================================
# Phase 2b: 订单闭环工具（list / detail / cancel / track / pay）
# ================================================================


class OrderListTool(Tool):
    """列出当前用户的订单（倒序，最多 limit 条）。"""

    spec = ToolSpec(
        name="order.list",
        category="order",
        permission="read",
        description="列出当前用户的订单（倒序）",
        parameters={
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 20}},
        },
    )

    async def run(self, ctx: ToolContext, limit: int = 20) -> ToolResult:
        try:
            from app.repositories.order_repo import get_order_repo

            orders = await get_order_repo().alist_by_user(ctx.user_id, limit=limit)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"order.list failed: {e}")
            return ToolResult(ok=False, message="暂时无法查看订单，请稍后再试～")
        if not orders:
            return ToolResult(message="还没有订单哦～去逛逛下单吧！")
        lines = [f"📋 你的订单（{len(orders)} 单）："]
        for idx, o in enumerate(orders, 1):
            oid = o.get("order_id", "")
            total = o.get("total_price", 0) or 0
            st = _STATUS_CN.get(o.get("status", ""), o.get("status", ""))
            created = (o.get("created_at", "") or "")[:10]
            lines.append(f"  {idx}. {oid}  ¥{total:.0f}  [{st}]  {created}")
        lines.append("说「订单详情」/「取消第N个」/「支付第N个」/「物流第N个」可对指定订单操作～")
        return ToolResult(message="\n".join(lines), data={"orders": orders})


class OrderDetailTool(Tool):
    """查看单个订单详情。"""

    spec = ToolSpec(
        name="order.detail",
        category="order",
        permission="read",
        description="查看单个订单详情",
        parameters={
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    )

    async def run(self, ctx: ToolContext, order_id: str = "") -> ToolResult:
        if not order_id:
            return ToolResult(ok=False, message="请先说「查看订单」看列表，再指定具体订单～")
        try:
            from app.repositories.order_repo import get_order_repo

            order = await get_order_repo().aget(order_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"order.detail failed: {e}")
            return ToolResult(ok=False, message="暂时无法查看订单详情，请稍后再试～")
        if not order:
            return ToolResult(ok=False, message=f"找不到订单 {order_id}～")
        items = order.get("items", []) or []
        total = order.get("total_price", 0) or 0
        st = _STATUS_CN.get(order.get("status", ""), order.get("status", ""))
        created = (order.get("created_at", "") or "").replace("T", " ")[:19]
        item_lines = []
        for i, it in enumerate(items, 1):
            b = it.get("brand", "")
            t = it.get("title", "")[:50]
            q = it.get("quantity", 1)
            p = it.get("price", 0)
            item_lines.append(f"  {i}. {b} {t} x{q}  ¥{p * q:.0f}")
        items_text = "\n".join(item_lines) if item_lines else "  （无商品信息）"
        text = f"📋 订单 {order_id}\n状态：{st}\n下单时间：{created}\n商品：\n{items_text}\n💰 合计：¥{total:.0f}"
        return ToolResult(message=text, data={"order": order})


class OrderCancelTool(Tool):
    """取消订单（需 _confirmed 确认）。"""

    spec = ToolSpec(
        name="order.cancel",
        category="order",
        permission="order",
        description="取消订单",
        parameters={
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    )

    async def run(self, ctx: ToolContext, order_id: str = "") -> ToolResult:
        if not order_id:
            return ToolResult(ok=False, message="请指定要取消的订单～")
        try:
            from app.repositories.order_repo import get_order_repo

            repo = get_order_repo()
            order = await repo.aget(order_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"order.cancel failed: {e}")
            return ToolResult(ok=False, message="取消失败，请稍后再试～")
        if not order:
            return ToolResult(ok=False, message=f"找不到订单 {order_id}～")
        cur = order.get("status", "")
        if cur == "cancelled":
            return ToolResult(ok=False, message=f"订单 {order_id} 已取消，无需重复～")
        if cur == "shipped":
            return ToolResult(ok=False, message=f"订单 {order_id} 已发货，无法取消～")
        ok = await repo.aupdate_status(order_id, "cancelled")
        if not ok:
            return ToolResult(ok=False, message="取消失败，请稍后再试～")
        # P2-1: 已支付订单取消附退款语义（模拟）
        if cur == "paid":
            return ToolResult(
                message=f"❎ 订单 {order_id} 已取消，货款将原路退回（模拟，1-3 个工作日到账）",
                data={"order_id": order_id, "refund": True},
            )
        return ToolResult(message=f"❎ 订单 {order_id} 已取消", data={"order_id": order_id})


class OrderTrackTool(Tool):
    """查询订单物流轨迹（经 LogisticsProvider）。"""

    spec = ToolSpec(
        name="order.track",
        category="order",
        permission="read",
        description="查询订单物流轨迹",
        parameters={
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    )

    async def run(self, ctx: ToolContext, order_id: str = "") -> ToolResult:
        if not order_id:
            return ToolResult(ok=False, message="请指定要查物流的订单～")
        try:
            from app.providers.tools.mocks import get_logistics_provider
            from app.repositories.order_repo import get_order_repo

            order = await get_order_repo().aget(order_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"order.track failed: {e}")
            return ToolResult(ok=False, message="暂时无法查询物流，请稍后再试～")
        if not order:
            return ToolResult(ok=False, message=f"找不到订单 {order_id}～")
        st = order.get("status", "")
        if st == "cancelled":
            return ToolResult(ok=False, message=f"订单 {order_id} 已取消，无物流～")
        if st == "pending":
            return ToolResult(ok=False, message=f"订单 {order_id} 还未支付，暂无物流～")
        track = await get_logistics_provider().track(order_id, order.get("created_at"))
        state_line = track.get("state", "")
        # P2-4: 刚支付首节点未达时，“待发货”改为更符合直觉的备货文案
        nodes = track.get("nodes", [])
        if st == "paid" and nodes and not nodes[0].get("done"):
            state_line = "已支付，商家备货中"
        lines = [f"📦 订单 {order_id}", f"📍 当前状态：{state_line}", "物流轨迹："]
        for node in nodes:
            mark = "✓" if node.get("done") else "⏳"
            t = node.get("time", "")
            suffix = f" · {t}" if t else ""
            lines.append(f"  {mark} {node.get('name', '')}{suffix}")
        eta = track.get("eta", "")
        if eta:
            lines.append(f"⏱️ {eta}")
        return ToolResult(message="\n".join(lines), data={"track": track})


class OrderPayTool(Tool):
    """支付订单（需 _confirmed 确认）。"""

    spec = ToolSpec(
        name="order.pay",
        category="order",
        permission="order",
        description="支付订单",
        parameters={
            "type": "object",
            "properties": {"order_id": {"type": "string"}, "method": {"type": "string"}},
            "required": ["order_id"],
        },
    )

    async def run(self, ctx: ToolContext, order_id: str = "", method: str = "mock") -> ToolResult:
        if not order_id:
            return ToolResult(ok=False, message="请指定要支付的订单～")
        try:
            from app.providers.tools.mocks import get_payment_provider
            from app.repositories.order_repo import get_order_repo

            repo = get_order_repo()
            order = await repo.aget(order_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"order.pay failed: {e}")
            return ToolResult(ok=False, message="支付失败，请稍后再试～")
        if not order:
            return ToolResult(ok=False, message=f"找不到订单 {order_id}～")
        cur = order.get("status", "")
        if cur == "paid":
            return ToolResult(ok=False, message=f"订单 {order_id} 已支付，无需重复～")
        if cur == "cancelled":
            return ToolResult(ok=False, message=f"订单 {order_id} 已取消，无法支付～")
        if cur != "pending":
            return ToolResult(ok=False, message=f"订单 {order_id} 状态 {cur}，不能支付～")
        result = await get_payment_provider().pay(order_id, method=method)
        if result.get("status") != "paid":
            return ToolResult(ok=False, message=f"支付失败：{result.get('error') or '未知错误'}")
        await repo.aupdate_status(order_id, "paid")
        return ToolResult(
            message=f"💳 支付成功！订单 {order_id} 已完成支付（{result.get('txn_id')}），感谢购买～",
            data={"order_id": order_id, "txn_id": result.get("txn_id")},
        )
