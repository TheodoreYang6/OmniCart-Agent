"""ShopActionAgent —— 购物动作编排层（会话感知）。

职责（渐进替代 ``agent_stream.py`` 的购物动作 if/elif，由 ``ENABLE_TOOL_ROUTER`` 控制）：
- 意图路由（pending_sku / confirm / 纯购物车 / order / address / add / 兜底）；
- 引用解析（focus_product / 序号→last_products / 购物车选中）；
- 多轮 pending 状态读写（pending_sku_product / pending_order_items，经 conv_svc）；
- 地址解析；调用纯工具（cart.* / order.*）完成实际仓库/格式化。

工具保持纯函数；本编排层承担全部会话感知逻辑。文案与 legacy 逐字对齐（A/B 对拍等价）。
"""

from __future__ import annotations

import logging

from app.framework.tools.ordinal import OrdinalResolver
from app.framework.tools.protocols import ToolContext, ToolResult

logger = logging.getLogger(__name__)

_CONFIRM = ["确认下单", "确认订单", "确认付款"]
_ORDER = ["下单", "结算", "结账", "买单", "付款"]
_ADDR = ["修改地址", "改地址", "换地址"]
_ADD = ["加入购物车", "加到购物车", "加进购物车", "加购", "全部加入"]

# Phase 2b 订单闭环 & 库存
_ORDER_LIST = ["我的订单", "订单列表", "查看订单", "看订单"]
_ORDER_DETAIL = ["订单详情"]
_ORDER_CANCEL = ["取消订单", "取消第"]
_ORDER_TRACK = ["物流", "查物流", "追踪"]
_ORDER_PAY = ["支付订单", "去支付", "支付第", "付款第"]
_INVENTORY = ["有货吗", "库存", "还有货", "缺货吗"]

# Phase 6-B3 偏好 & 会话
_PREF_DELETE = ["删除第一条偏好", "删除偏好", "删掉偏好"]  # 含序号句式另行处理
_PREF_LIST = ["我的偏好", "偏好列表", "查看偏好", "记住了什么"]
_PREF_SAVE = ["记住我", "记一下我", "以后推荐", "以后都", "别再推", "不要推荐"]
_CONV_HISTORY = ["聊了什么", "刚才说了什么", "对话历史", "聊天记录"]
_CONV_RESET = ["重新开始", "清空上下文", "换个话题重来", "重置对话"]

# Phase 6-B4 语义技能（PromptSkill）
_SKILL_COPY = ["写个文案", "写文案", "种草文案", "帮我种草"]


class ShopActionAgent:
    """购物动作 Agent —— msg + ctx → ToolResult。"""

    async def handle(self, msg: str, ctx: ToolContext) -> ToolResult:
        from app.framework.tools.dispatcher import RuleToolRouter
        from app.providers.tools import get_tool_registry

        # Phase 3 A2A：请求级黑板（工具 Artifact 经 registry 自动落板，如 order.created）
        if ctx.blackboard is None:
            from app.framework.blackboard import Blackboard

            ctx.blackboard = Blackboard()

        registry = get_tool_registry()
        conv = self._conv_svc()
        cid, uid = ctx.conversation_id, ctx.user_id

        snap = await self._snapshot(conv, cid)
        pending_sku = snap.get("pending_sku_product") or {}
        focus = snap.get("focus_product") or {}
        last_products = snap.get("last_products") or []
        last_orders = snap.get("last_orders") or []

        # 1. pending_sku 解析（用户点了规格选项 / 回复规格）
        if pending_sku:
            res = await self._handle_pending_sku(registry, ctx, conv, cid, msg, pending_sku)
            if res is not None:
                return res  # 未匹配 SKU 时返回 None → 落到后续 handler（legacy fall-through）

        # 2. 确认下单（须在 order 之前："确认下单" 含 "下单"）
        if any(k in msg for k in _CONFIRM) or msg.strip() == "确认":
            return await self._handle_confirm(registry, ctx, uid, focus, last_products)

        # 3. Phase 6-B3：偏好 & 会话（须在 RuleToolRouter 前："删除第2条偏好" 含 "删除第"，
        # 会被 cart.remove 抢走；"聊了什么" 等无冲突但同族集中处理）
        if "偏好" in msg and any(k in msg for k in ("删除", "删掉", "去掉")):
            return await self._handle_pref_delete(registry, ctx, msg)
        if any(k in msg for k in _PREF_LIST):
            return await registry.invoke("preference.list", {}, ctx)
        if any(k in msg for k in _PREF_SAVE):
            return await registry.invoke("preference.save", {"raw_text": msg}, ctx)
        if any(k in msg for k in _CONV_HISTORY):
            return await registry.invoke("conversation.history", {}, ctx)
        if any(k in msg for k in _CONV_RESET):
            return await registry.invoke("conversation.reset", {}, ctx)
        # Phase 6-B4：语义技能（种草文案，PromptSkill 而非 Tool）
        if any(k in msg for k in _SKILL_COPY):
            return await self._handle_copywriter(msg, focus, last_products)

        # 4. 纯购物车（view / remove / update_qty / clear）
        name, args = RuleToolRouter().match(msg, ctx)
        if name:
            return await registry.invoke(name, args or {}, ctx)

        # 4. Phase 2b：订单闭环 & 库存查询（须在 _ORDER 前，避免 "付款第" 被 "付款" 抢走）
        if any(k in msg for k in _ORDER_DETAIL):
            return await self._handle_order_detail(registry, ctx, msg, last_orders)
        if any(k in msg for k in _ORDER_LIST):
            return await self._handle_order_list(registry, ctx, conv, cid)
        if any(k in msg for k in _ORDER_CANCEL):
            return await self._handle_order_cancel(registry, ctx, msg, last_orders)
        if any(k in msg for k in _ORDER_TRACK):
            return await self._handle_order_track(registry, ctx, msg, last_orders)
        if any(k in msg for k in _ORDER_PAY):
            return await self._handle_order_pay(registry, ctx, msg, last_orders)
        if any(k in msg for k in _INVENTORY):
            return await self._handle_check_inventory(registry, ctx, msg, focus, last_products)

        # 5. 下单（触发确认卡片）
        if any(k in msg for k in _ORDER):
            return await self._handle_order(registry, ctx, conv, cid, uid, msg, focus, last_products)

        # 6. 修改地址
        if any(k in msg for k in _ADDR):
            return ToolResult(
                message="好的～在下方填写新地址，填好后告诉我「下单」就行！",
                actions=[{"type": "address_form", "label": "填写新地址"}],
            )

        # 7. 加购
        if any(k in msg for k in _ADD):
            return await self._handle_add(registry, ctx, conv, cid, msg, focus, last_products)

        # 8. LLM 函数调用兜底（Phase 6-B1）：关键词未命中时让 LLM 从白名单工具选择；
        # flag 默认关 / MOCK 惰性 / 无匹配 → 落原兜底提示
        from app.core.config import ENABLE_LLM_TOOL_CALLING

        if ENABLE_LLM_TOOL_CALLING:
            from app.framework.tools.dispatcher import ToolDispatcher

            res = await ToolDispatcher(registry).dispatch(msg, ctx)
            if res.ok:
                return res

        # 9. 兜底
        return ToolResult(message="好的～你可以对商品点「问欧米」后说「下单」来直接结算哦！")

    # ================================================================
    # Handlers
    # ================================================================

    async def _handle_pref_delete(self, registry, ctx, msg):
        """删除偏好：序号 → preference.list 取 entry_id → preference.delete。"""
        n = OrdinalResolver.parse_ordinal(msg, r"第") or 1
        listing = await registry.invoke("preference.list", {}, ctx)
        entries = (listing.data or {}).get("entries") or []
        if not entries:
            return ToolResult(message="还没有记录过偏好哦～")
        if not (1 <= n <= len(entries)):
            return ToolResult(ok=False, message=f"只有 {len(entries)} 条偏好哦～")
        entry_id = entries[n - 1].get("entry_id") or entries[n - 1].get("id") or ""
        return await registry.invoke("preference.delete", {"entry_id": entry_id}, ctx)

    async def _handle_copywriter(self, msg, focus, last_products):
        """种草文案（PromptSkill）：focus → 序号 → 上轮 Top1 解析目标商品。"""
        target = None
        if focus.get("product_id"):
            target = focus
        elif last_products:
            n = OrdinalResolver.parse_ordinal(msg, r"第")
            if n and 1 <= n <= len(last_products):
                target = last_products[n - 1]
            else:
                target = last_products[0]
        if not target:
            return ToolResult(message="先告诉我写哪个商品呀～可以先让我推荐，或对商品点「问欧米」再说「写个文案」")
        info = (f"商品：{target.get('brand', '')} {target.get('title', '')}\n"
                f"价格：¥{target.get('price', 0)}")
        try:
            from app.providers.skills import get_skill_registry

            text = await get_skill_registry().get("copywriter.product").run(product_info=info)
        except Exception as e:  # noqa: BLE001 — 技能失败降级友好提示
            logger.warning(f"copywriter skill failed: {e}")
            return ToolResult(ok=False, message="文案生成失败，稍后再试试～")
        t = (target.get("brand", "") + " " + target.get("title", ""))[:40]
        return ToolResult(message=f"✨ 「{t}」种草文案：\n\n{text.strip()}",
                          data={"skill": "copywriter.product"})

    async def _handle_pending_sku(self, registry, ctx, conv, cid, msg, pending_sku):
        pid = pending_sku.get("product_id", "")
        if not pid:
            return None
        from app.repositories.product_repo import get_product_repo

        product = get_product_repo().get_by_id(pid)
        if not (product and product.skus):
            return None
        best_sku, best_score = self._match_sku(product, msg)
        if not (best_sku and best_score > 0):
            return None  # 未匹配 → fall-through（对齐 legacy）
        res = await registry.invoke("cart.add", {
            "product_id": pid,
            "sku_id": best_sku.sku_id,
            "title": pending_sku.get("title") or product.title,
            "brand": pending_sku.get("brand") or product.brand,
            # price 不传 → cart.add 用 sku.price 或 product.base_price（对齐 legacy）
        }, ctx)
        await self._update_snapshot(conv, cid, {"pending_sku_product": None})
        return res

    async def _handle_confirm(self, registry, ctx, uid, focus, last_products):
        items, source = await self._resolve_confirm_items(uid, focus, last_products)
        if not items:
            return ToolResult(message="没有找到要下单的商品～")
        addr = await self._resolve_address(uid)
        if not addr:
            return ToolResult(
                message="还没有收货地址～点下方按钮填写后再说「下单」就行！",
                actions=[{"type": "address_form", "label": "填写收货地址"}],
            )
        res = await registry.invoke(
            "order.submit", {"items": items, "address": addr, "_confirmed": True}, ctx
        )
        if source != "focus":  # 非 focus 来源结算后清空购物车（对齐 legacy）
            await registry.invoke("cart.clear", {}, ctx)
        return res

    async def _handle_order(self, registry, ctx, conv, cid, uid, msg, focus, last_products):
        items, source = await self._resolve_order_items(uid, msg, focus, last_products)
        if not items:
            return ToolResult(message="请先去浏览商品、加入购物车，或者点「问欧米」分析后再说「下单」哦～")
        addr = await self._resolve_address(uid)
        res = await registry.invoke("order.preview", {"items": items, "address": addr}, ctx)
        if source and res.data.get("pending_order_items"):
            await self._update_snapshot(conv, cid, {"pending_order_items": res.data["pending_order_items"]})
        return res

    async def _handle_add(self, registry, ctx, conv, cid, msg, focus, last_products):
        target = self._focus_target(focus)
        if not target and last_products:
            n = OrdinalResolver.parse_ordinal(msg, r"第")
            if n and 1 <= n <= len(last_products):
                target = self._product_target(last_products[n - 1])
            elif not n:
                if "全部" in msg:
                    added = 0
                    for p in last_products[:5]:
                        r = await registry.invoke("cart.add", {
                            "product_id": p.get("product_id", ""), "sku_id": "",
                            "title": p.get("title", ""), "brand": p.get("brand", ""),
                            "price": p.get("price", 0),
                        }, ctx)
                        if r.ok:
                            added += 1
                    return ToolResult(message=f"✅ 已把 {added} 件商品加入购物车～")
                target = self._product_target(last_products[0])
        if not target:
            return ToolResult(message="请先说你想买什么，我再帮你加购哦～")
        res = await registry.invoke("cart.add", {
            "product_id": target["product_id"], "title": target["title"],
            "brand": target["brand"], "price": target["price"],
            # sku_id 不传(None) → 多规格触发 needs_sku
        }, ctx)
        if res.data.get("needs_sku"):
            await self._update_snapshot(conv, cid, {"pending_sku_product": res.data["needs_sku"]})
        return res

    # ================================================================
    # Phase 2b: 订单闭环 & 库存 handlers
    # ================================================================

    async def _handle_order_list(self, registry, ctx, conv, cid):
        res = await registry.invoke("order.list", {}, ctx)
        orders = (res.data or {}).get("orders", [])
        order_ids = [o.get("order_id", "") for o in orders if o.get("order_id")]
        if order_ids:
            await self._update_snapshot(conv, cid, {"last_orders": order_ids})
        return res

    async def _handle_order_detail(self, registry, ctx, msg, last_orders):
        oid = self._resolve_order_id(msg, last_orders)
        if not oid:
            return ToolResult(ok=False, message="请先说「查看订单」看列表，再说「订单详情」或「第N个」～")
        return await registry.invoke("order.detail", {"order_id": oid}, ctx)

    async def _handle_order_cancel(self, registry, ctx, msg, last_orders):
        oid = self._resolve_order_id(msg, last_orders)
        if not oid:
            return ToolResult(ok=False, message="请先说「查看订单」看列表，再说「取消第N个」～")
        return await registry.invoke("order.cancel", {"order_id": oid, "_confirmed": True}, ctx)

    async def _handle_order_track(self, registry, ctx, msg, last_orders):
        oid = self._resolve_order_id(msg, last_orders)
        if not oid:
            return ToolResult(ok=False, message="请先说「查看订单」看列表，再说「物流第N个」～")
        return await registry.invoke("order.track", {"order_id": oid}, ctx)

    async def _handle_order_pay(self, registry, ctx, msg, last_orders):
        oid = self._resolve_order_id(msg, last_orders)
        if not oid:
            return ToolResult(ok=False, message="请先说「查看订单」看列表，再说「支付第N个」～")
        return await registry.invoke("order.pay", {"order_id": oid, "_confirmed": True}, ctx)

    async def _handle_check_inventory(self, registry, ctx, msg, focus, last_products):
        pid = self._resolve_product_id_for_inventory(msg, focus, last_products)
        if not pid:
            return ToolResult(ok=False, message="请先看看商品哦～")
        return await registry.invoke("shopping.check_inventory", {"product_id": pid}, ctx)

    @staticmethod
    def _resolve_order_id(msg, last_orders):
        """正则 ORD-XXXXXXXX → 序号 last_orders[n-1] → last_orders[0] → None。"""
        import re
        m = re.search(r"ORD-[A-F0-9]{8}", msg)
        if m:
            return m.group(0)
        n = OrdinalResolver.parse_ordinal(msg, r"第")
        if n and last_orders and 1 <= n <= len(last_orders):
            return last_orders[n - 1]
        if last_orders:
            return last_orders[0]
        return None

    @staticmethod
    def _resolve_product_id_for_inventory(msg, focus, last_products):
        """focus → 序号 last_products[n-1] → last_products[0] → None。"""
        if focus.get("product_id"):
            return focus["product_id"]
        n = OrdinalResolver.parse_ordinal(msg, r"第")
        if n and last_products and 1 <= n <= len(last_products):
            return last_products[n - 1].get("product_id", "")
        if last_products:
            return last_products[0].get("product_id", "")
        return None

    # ================================================================
    # 引用解析
    # ================================================================

    async def _resolve_confirm_items(self, uid, focus, last_products):
        """确认下单来源：focus → 购物车选中 → last_products[0]（对齐 legacy）。"""
        if focus.get("product_id"):
            return [self._focus_item(focus)], "focus"
        sel = await self._cart_selected_items(uid)
        if sel:
            return sel, "cart"
        if last_products:
            return [self._last_item(last_products[0])], "last"
        return [], ""

    async def _resolve_order_items(self, uid, msg, focus, last_products):
        """下单来源：focus → 序号 last_products → 购物车选中（对齐 legacy）。"""
        if focus.get("product_id"):
            return [self._focus_item(focus)], "focus"
        n = OrdinalResolver.parse_ordinal(msg, r"第")
        if n and last_products and 1 <= n <= len(last_products):
            return [self._last_item(last_products[n - 1])], "last"
        sel = await self._cart_selected_items(uid)
        if sel:
            return sel, "cart"
        return [], ""

    async def _cart_selected_items(self, uid):
        try:
            from app.repositories.pg_cart_repo import get_cart_repo

            cart = await get_cart_repo().aget_cart(uid)
            return [
                {"product_id": i.product_id, "title": i.title, "brand": i.brand,
                 "price": i.price, "quantity": i.quantity}
                for i in cart.items if i.selected
            ]
        except Exception:  # noqa: BLE001
            return []

    @staticmethod
    def _focus_item(focus):
        return {"product_id": focus.get("product_id", ""), "title": focus.get("title", ""),
                "brand": focus.get("brand", ""), "price": focus.get("price", 0), "quantity": 1}

    @staticmethod
    def _last_item(p):
        return {"product_id": p.get("product_id", ""), "title": p.get("title", ""),
                "brand": p.get("brand", ""), "price": p.get("price", 0), "quantity": 1}

    @staticmethod
    def _focus_target(focus):
        if not focus.get("product_id"):
            return None
        return {"product_id": focus.get("product_id", ""), "title": focus.get("title", ""),
                "brand": focus.get("brand", ""), "price": focus.get("price", 0)}

    @staticmethod
    def _product_target(p):
        return {"product_id": p.get("product_id", ""), "title": p.get("title", ""),
                "brand": p.get("brand", ""), "price": p.get("price", 0)}

    @staticmethod
    def _match_sku(product, msg):
        """按 msg 中出现的规格属性打分匹配 SKU（对齐 legacy 评分逻辑）。"""
        best_sku, best_score = None, 0
        for s in product.skus:
            score = 0
            for k, v in (s.properties or {}).items():
                if k in msg and v in msg:
                    score += 2
                elif v in msg:
                    score += 1
            if score > best_score:
                best_score, best_sku = score, s
        return best_sku, best_score

    # ================================================================
    # 地址 / 会话快照
    # ================================================================

    async def _resolve_address(self, uid):
        """获取默认地址（兼容 async/sync 仓库）。

        P1-1 数据隔离：DEMO_USER_ID 兜底仅限 uid 为空（匿名 demo 客户端）；
        实名用户无地址时直接返 None 走「填写收货地址」流程，不再借用 demo 地址。
        """
        from app.schemas.cart import DEMO_USER_ID

        if not uid:
            uid = DEMO_USER_ID
        try:
            from app.repositories.address_repo import get_address_repo

            repo = get_address_repo()
            if hasattr(repo, "_alist"):
                addrs = await repo._alist(uid)
            else:
                addrs = repo.list(uid)
            return next((a for a in addrs if a.get("is_default")), addrs[0] if addrs else None)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"resolve address failed for {uid}: {e}")
            return None

    @staticmethod
    def _conv_svc():
        try:
            from app.services.conversation_service import get_conversation_service

            return get_conversation_service()
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    async def _snapshot(conv, cid) -> dict:
        if not (conv and cid):
            return {}
        try:
            return (await conv.get_context_snapshot(cid)) or {}
        except Exception:  # noqa: BLE001
            return {}

    @staticmethod
    async def _update_snapshot(conv, cid, updates: dict) -> None:
        if not (conv and cid):
            return
        try:
            await conv.aupdate_context_snapshot(cid, updates)
        except Exception:  # noqa: BLE001
            pass
