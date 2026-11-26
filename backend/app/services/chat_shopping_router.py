"""Bind model shopping decisions to account-owned objects and existing tools."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from app.agents.shop_action_agent import ShopActionAgent
from app.core.config import settings
from app.framework.tools import ToolContext, ToolResult
from app.providers.tools import get_tool_registry
from app.services.chat_shopping_intent import ShoppingIntent, understand_shopping_turn

logger = logging.getLogger(__name__)


def _context_time(value: str) -> datetime:
    try:
        value_at = datetime.fromisoformat(value)
        return value_at if value_at.tzinfo is not None else value_at.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)


@dataclass
class ShoppingContext:
    snapshot: dict = field(default_factory=dict)
    recent: list[dict] = field(default_factory=list)
    cart: list = field(default_factory=list)
    found: list[dict] = field(default_factory=list)
    products: dict = field(default_factory=dict)
    orders: dict = field(default_factory=dict)
    order_details: dict = field(default_factory=dict)
    cart_items: dict = field(default_factory=dict)
    cart_refs: dict = field(default_factory=dict)
    skus: dict = field(default_factory=dict)

    def model_context(self, completed: list[dict]) -> dict:
        last = self.snapshot.get("last_products") or []
        focus = self.snapshot.get("focus_product") or {}
        pending = self.snapshot.get("pending_sku_product") or {}
        if focus.get("product_id") and focus.get("locked_at"):
            # Older single-product turns only wrote the focus. Their last_products
            # can still describe cards from a different, earlier recommendation.
            latest_cards = next((item for item in reversed(self.recent)
                                 if item.get("role") == "assistant" and item.get("product_refs")), {})
            locked_at = _context_time(focus["locked_at"])
            cards_at = _context_time(latest_cards.get("created_at"))
            if cards_at <= locked_at and self.snapshot.get("last_products_at") != focus["locked_at"]:
                last = [focus]
            elif cards_at > locked_at and focus["product_id"] not in latest_cards.get("product_refs", []):
                focus = {}
        self.products = {
            f"p{index}": product for index, product in enumerate(last[:10], 1)
            if isinstance(product, dict) and product.get("product_id")
        }
        for key, product in (("focus", focus), ("pending", pending)):
            if isinstance(product, dict) and product.get("product_id"):
                self.products[key] = product
        self.products.update({
            f"found{index}": product for index, product in enumerate(self.found[:8], 1)
            if product.get("product_id")
        })
        self.orders = {f"o{i}": oid for i, oid in enumerate((self.snapshot.get("last_orders") or [])[:30], 1)}
        self.cart_items = {}
        for item in self.cart[:30]:
            if item.cart_item_id not in self.cart_refs:
                self.cart_refs[item.cart_item_id] = f"c{len(self.cart_refs) + 1}"
            self.cart_items[self.cart_refs[item.cart_item_id]] = item
        return {
            "recent": [{"role": item.get("role"), "text": str(item.get("content") or "")[:300]}
                       for item in self.recent[-6:]],
            "products": {
                ref: {"title": str(item.get("title") or item.get("name") or "")[:100],
                      "price": item.get("price", item.get("base_price"))}
                for ref, item in self.products.items()
            },
            "cart": {ref: {"title": item.title[:100], "sku": item.sku_label, "quantity": item.quantity}
                     for ref, item in self.cart_items.items()},
            "orders": {ref: self.order_details.get(oid, {}) for ref, oid in self.orders.items()},
            "pending_skus": {ref: label for ref, (_, label) in self.skus.items()},
            "pending_question": str(self.snapshot.get("pending_question") or "")[:200],
            "completed": completed,
        }


async def _cart_items(user_id: str) -> list:
    from app.repositories.pg_cart_repo import get_cart_repo

    try:
        return (await get_cart_repo().aget_cart(user_id)).items
    except Exception as exc:
        logger.warning("Shopping context cart unavailable (%s)", type(exc).__name__)
        return []


async def _conversation(conv, ctx: ToolContext) -> dict:
    if not conv or not ctx.conversation_id:
        return {}
    try:
        return await conv.aget_context(ctx.conversation_id, limit=7, user_id=ctx.user_id)
    except Exception as exc:
        logger.warning("Shopping conversation context unavailable (%s)", type(exc).__name__)
        return {}


async def _shopping_context(conv, ctx: ToolContext, *, authenticated: bool) -> ShoppingContext:
    if not authenticated:
        return ShoppingContext()
    history, cart = await asyncio.gather(_conversation(conv, ctx), _cart_items(ctx.user_id))
    recent = history.get("recent_messages") or []
    if recent and recent[-1].get("role") == "user" and recent[-1].get("content") == ctx.args_raw[:300]:
        recent = recent[:-1]
    context = ShoppingContext(snapshot=history.get("context_snapshot") or {}, recent=recent, cart=cart)
    pending = context.snapshot.get("pending_sku_product") or {}
    legacy_products = list(context.snapshot.get("last_products") or [])
    if any(isinstance(item, str) for item in legacy_products) or pending.get("product_id"):
        from app.repositories.product_repo import get_product_repo

        repository = get_product_repo()
        for index, entry in enumerate(legacy_products[:10]):
            if isinstance(entry, str):
                product = repository.get_by_id(entry)
                legacy_products[index] = {"product_id": entry, "title": product.title, "price": product.base_price} if product else {}
        context.snapshot["last_products"] = legacy_products
        product = repository.get_by_id(pending["product_id"]) if pending.get("product_id") else None
        if product and product.skus:
            context.skus = {
                f"s{i}": (sku.sku_id, " · ".join(str(value) for value in (sku.properties or {}).values()))
                for i, sku in enumerate(product.skus, 1)
            }
            context.skus["s0"] = ("", "默认规格")
    return context


def _reply(message: str, label: str = "", route: str = "", *, ok: bool = True) -> ToolResult:
    actions = [{"type": "quick_reply", "label": label, "route": route}] if route else []
    return ToolResult(ok=ok, message=message, actions=actions)


_READ_OR_EXPLICIT = {
    "cart.view", "cart.clear", "preference.list", "conversation.history", "conversation.reset",
}


async def _execute(
    intent: ShoppingIntent, shopping: ShoppingContext, ctx: ToolContext, conv, *, payment_available: bool,
) -> ToolResult:
    action = intent.action
    registry = get_tool_registry()
    if action in _READ_OR_EXPLICIT:
        return await registry.invoke(action, {}, ctx)
    if action == "address.edit":
        return ToolResult(message="请填写或修改收货地址。", actions=[{"type": "address_form", "label": "修改地址"}])
    if action == "preference.save":
        return await registry.invoke(action, {"raw_text": ctx.args_raw}, ctx)
    if action == "preference.delete":
        if intent.ordinal is None:
            return _reply("你想删除哪一条偏好？", ok=False)
        listing = await registry.invoke("preference.list", {}, ctx)
        entries = listing.data.get("entries") or []
        if intent.ordinal > len(entries):
            return _reply("没有找到这条偏好，请先查看偏好列表。", ok=False)
        entry = entries[intent.ordinal - 1]
        return await registry.invoke(action, {"entry_id": entry.get("entry_id") or entry.get("id")}, ctx)
    if action == "order.list":
        return await ShopActionAgent()._handle_order_list(registry, ctx, conv, ctx.conversation_id)
    if action in {"order.detail", "order.track", "order.cancel", "order.pay"}:
        order_id = shopping.orders.get(intent.order)
        if not order_id:
            return _reply("请先查看订单列表，再告诉我你指的是哪一笔。", ok=False)
        if action in {"order.cancel", "order.pay"}:
            from app.services.shop_action_confirmation import offer_order_confirmation

            return await offer_order_confirmation(ctx.user_id, action, order_id)
        return await registry.invoke(action, {"order_id": order_id}, ctx)
    if action == "order.preview":
        items = [item.model_dump() for item in shopping.cart if item.selected]
        if not items or intent.product:
            return _reply("请把要购买的商品加入购物车，并勾选后核对订单。", "打开购物车", "cart")
        address = await ShopActionAgent()._resolve_address(ctx.user_id)
        preview = await registry.invoke(action, {"items": items, "address": address}, ctx)
        preview.actions = [entry for entry in preview.actions if entry.get("type") == "address_form"]
        preview.actions.insert(0, {"type": "quick_reply", "label": "核对购物车并下单", "route": "cart"})
        return preview
    if action.startswith("payment."):
        if not payment_available:
            return _reply("当前聊天没有启用支付宝结算。", "打开购物车", "cart", ok=False)
        from app.providers.tools.cart_payment import OPEN, QUOTE, STATUS, cart_payment_tools

        tool = {"payment.quote": QUOTE, "payment.confirm": OPEN, "payment.status": STATUS}[action]
        return await cart_payment_tools().invoke(tool, {}, ctx)
    if action in {"cart.remove", "cart.update_qty"}:
        item = shopping.cart_items.get(intent.cart)
        if item is None or (action == "cart.update_qty" and intent.quantity is None):
            return _reply("请告诉我是哪件购物车商品，以及要改成的数量（如需改数量）。", ok=False)
        args = {"cart_item_id": item.cart_item_id}
        if action == "cart.update_qty":
            args["quantity"] = intent.quantity
        return await registry.invoke(action, args, ctx)
    if action == "product.search":
        if not intent.query.strip() or not intent.continue_after:
            return _reply("请告诉我你想先找哪类商品。", ok=False)
        result = await registry.invoke("shopping.search", {"query": intent.query, "budget_max": intent.budget_max}, ctx)
        shopping.found = (result.data.get("products") or [])[:5]
        if not shopping.found:
            return _reply("没有找到符合这些条件的商品。", ok=False)
        latest = {"last_products": shopping.found, "focus_product": {}}
        shopping.snapshot.update(latest)
        if conv and ctx.conversation_id:
            await conv.aupdate_context_snapshot(ctx.conversation_id, latest, user_id=ctx.user_id)
        labels = [f"{i}. {str(item.get('title') or item.get('name') or '')[:70]}"
                  for i, item in enumerate(shopping.found, 1)]
        return _reply("\n".join(["找到这些商品：", *labels]))

    if action == "cart.select_sku":
        product = shopping.products.get("pending")
        sku = shopping.skus.get(intent.sku)
        if not product or not sku:
            return _reply("请告诉我你要选哪个规格。", ok=False)
        pending = shopping.snapshot["pending_sku_product"]
        args = {"product_id": product["product_id"], "sku_id": sku[0], "quantity": pending.get("quantity", 1)}
        if settings.use_postgres:
            args["pending_selection_id"] = pending.get("selection_id", "")
        result = await registry.invoke("cart.add", args, ctx)
        if result.ok and conv and ctx.conversation_id:
            if settings.use_postgres:
                conv.invalidate_context_snapshot(ctx.conversation_id, user_id=ctx.user_id)
            else:
                await conv.aupdate_context_snapshot(ctx.conversation_id, {"pending_sku_product": None}, user_id=ctx.user_id)
        return result

    selected = [shopping.products.get(ref) for ref in intent.product]
    if not selected or any(product is None for product in selected):
        return _reply("你想操作哪一款商品？", ok=False)
    products = {product["product_id"]: product for product in selected}
    if action == "inventory.check" and len(products) == 1:
        return await registry.invoke("shopping.check_inventory", {"product_id": next(iter(products))}, ctx)
    if action == "product.copy" and len(products) == 1:
        return await ShopActionAgent()._handle_copywriter("", next(iter(products.values())), [])
    if action != "cart.add":
        return _reply("请指定一款商品。", ok=False)

    added = []
    for product_id in products:
        result = await registry.invoke("cart.add", {"product_id": product_id, "quantity": intent.quantity or 1}, ctx)
        pending = result.data.get("needs_sku")
        if pending and conv and ctx.conversation_id:
            selection_id = uuid4().hex
            await conv.aupdate_context_snapshot(ctx.conversation_id, {
                "pending_sku_product": {**pending, "quantity": intent.quantity or 1, "selection_id": selection_id},
            }, user_id=ctx.user_id)
            if settings.use_postgres:
                result.data["shop_card"]["payload"]["selection_id"] = selection_id
                for option in result.actions:
                    option["selection_id"] = selection_id
        if pending or not result.ok:
            result.message = "\n".join([*added, result.message])
            result.data["cart_changed"] = bool(added)
            return result
        added.append(result.message)
    result.message = "\n".join(added)
    return result


async def run_shopping_turn(
    ctx: ToolContext, conv, *, authenticated: bool, payment_available: bool, catalogue_only: bool = False,
) -> ToolResult | None:
    """Return None when the model hands the turn to recommendation or general chat."""
    try:
        shopping = await _shopping_context(conv, ctx, authenticated=authenticated and not catalogue_only)
    except Exception as exc:
        logger.warning("Shopping context unavailable (%s)", type(exc).__name__)
        shopping = ShoppingContext()
    results = []
    completed = []
    executed = []
    cart_changed = False
    for _ in range(3):
        intent = await understand_shopping_turn(ctx.args_raw, shopping.model_context(completed))
        if intent is None:
            if catalogue_only or (settings.mock_mode and not results):
                return None
            reason = ("后续动作暂时无法确认，已停止执行剩余步骤。"
                      if results else "购物操作识别暂时不可用，这次没有执行任何操作。请重试。")
            return ToolResult(ok=False, message="\n".join([*results, reason]), data={"cart_changed": cart_changed})
        if intent.action == "workflow" or catalogue_only:
            if not results:
                return None
            return ToolResult(message="\n".join(results), data={
                "workflow_after": True, "cart_changed": cart_changed, "workflow_query": intent.query,
            })
        if intent.action == "clarify":
            return ToolResult(message="\n".join([*results, intent.question or "你想让我做哪一步？"]),
                              data={"cart_changed": cart_changed})
        if intent.action == "report.open":
            text = "选购报告可以在报告页选择品类和预算。"
            if settings.report_payment_mode == "disabled" or not settings.use_postgres:
                text = "选购报告暂未开放收款。"
            report = _reply("\n".join([*results, text]), "查看选购报告", "reports?source=agent")
            report.data["cart_changed"] = cart_changed
            return report
        if not authenticated:
            return ToolResult(message="登录后我就能帮你操作购物车和订单。", data={"requires_login": True},
                              actions=[{"type": "login", "label": "登录后继续", "route": "login"}])
        signature = intent.model_dump(exclude={"continue_after", "question"})
        cart_item = shopping.cart_items.get(intent.cart)
        product_ids = tuple(sorted({
            shopping.products.get(ref, {}).get("product_id", ref) for ref in intent.product
        }))
        cart_item_id = cart_item.cart_item_id if cart_item else intent.cart
        order_id = shopping.orders.get(intent.order, intent.order)
        arguments = {
            "cart.add": (product_ids, intent.quantity or 1),
            "cart.select_sku": (shopping.products.get("pending", {}).get("product_id"), intent.sku),
            "cart.update_qty": (cart_item_id, intent.quantity),
            "cart.remove": cart_item_id,
            "order.detail": order_id,
            "order.track": order_id,
            "order.cancel": order_id,
            "order.pay": order_id,
            "inventory.check": product_ids,
            "product.copy": product_ids,
            "product.search": (intent.query.strip(), intent.budget_max),
            "preference.delete": intent.ordinal,
        }
        key = (intent.action, arguments.get(intent.action))
        if key in executed:
            break
        executed.append(key)
        try:
            result = await _execute(intent, shopping, ctx, conv, payment_available=payment_available)
        except Exception as exc:
            logger.warning("Shopping operation %s did not complete (%s)", intent.action, type(exc).__name__)
            result = _reply("暂时无法确认这一步的结果，请先核对状态。", ok=False)
        results.append(result.message or "这一步未能完成。")
        needs_input = result.data.get("needs_sku") or intent.action in {
            "order.preview", "order.cancel", "order.pay", "payment.confirm", "address.edit",
        }
        cart_changed = cart_changed or bool(result.data.get("cart_changed")) or (
            result.ok and not needs_input and intent.action in {
                "cart.add", "cart.select_sku", "cart.update_qty", "cart.remove", "cart.clear",
            }
        )
        if not intent.continue_after or not result.ok or needs_input:
            result.data["cart_changed"] = cart_changed
            return result.model_copy(update={"message": "\n".join(results)})
        completed.append({"intent": signature, "result": result.message[:300]})
        if intent.action.startswith("cart."):
            shopping.cart = await _cart_items(ctx.user_id)
        if intent.action == "order.list":
            orders = [order for order in result.data.get("orders", []) if order.get("order_id")]
            shopping.snapshot["last_orders"] = [order["order_id"] for order in orders]
            shopping.order_details = {
                order["order_id"]: {"status": order.get("status"), "created_at": order.get("created_at"),
                                    "items": [item.get("title", "") for item in (order.get("items") or [])[:5]]}
                for order in orders
            }
    return ToolResult(message="\n".join([*results, "如果还有下一步，请告诉我。"]),
                      data={"cart_changed": cart_changed})
