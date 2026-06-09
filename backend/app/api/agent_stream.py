"""SSE 流式端点 — 正常推荐 / 商品聚焦分析 / 直接下单"""
import asyncio, json, logging, uuid as _uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.workflow.graph import run_workflow
from app.schemas.cart import DEMO_USER_ID

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recommend", tags=["stream"])


class StreamRequest(BaseModel):
    session_id: str = ""
    user_id: str = ""
    conversation_id: str = ""
    message: str = ""
    image_url: str | None = None
    mode: str = "normal_recommend"
    target_product_id: str | None = None
    allow_same_category_comparison: bool = False
    fast_mode: bool = False  # 快速回答：跳过LLM，直接模板回复


def _sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


_LEVEL_CN = {
    "strong_recommend": "强烈推荐", "recommended": "值得推荐",
    "cautious": "谨慎考虑", "insufficient_evidence": "证据不足",
    "not_recommended": "不推荐",
}


# ============================================================
# 辅助: 上下文增强
# ============================================================

def _extract_question(answer: str) -> str | None:
    """从豆仔回复中提取问句，供下一轮 Router 做问答链匹配。

    只匹配真正的问句 — 以？结尾，或以"吗/吧"结尾的疑问句。
    排除"呢"结尾的句子（"豆仔帮你盯着呢"不是问句）。
    """
    import re
    # 匹配: ?/？结尾 或 "吗/吧"结尾 → 真正的问题
    # 排除: "呢"结尾的陈述句 ("盯着呢""看着呢"等)
    sentence_pattern = re.compile(r'[^。！？\n]+(?:[？?]|[吗吧](?:[？?]|$))')
    matches = sentence_pattern.findall(answer)
    if matches:
        q = matches[-1].strip()
        return q if len(q) <= 120 else None
    return None


async def _generate_title(cid: str, conv_svc, first_query: str, first_answer: str):
    """后台异步生成对话标题。LLM 失败时降级为首条消息前15字。"""
    if not cid or not first_query:
        return
    title = ""
    try:
        from app.core.config import MOCK_MODE
        if not MOCK_MODE:
            from app.model_gateway.gateway import get_model_gateway
            gateway = get_model_gateway()
            prompt = (
                "用8字以内的中文给这段购物对话起个标题，只输出标题：\n"
                f"用户：{first_query[:60]}\n豆仔：{first_answer[:80]}"
            )
            title = (await gateway.chat("chat_generation", prompt)).strip()
            if title and len(title) > 15:
                title = title[:15]  # 截断过长的标题
    except Exception:
        pass
    # 降级：首条消息截取
    if not title:
        title = first_query.strip()[:15]
    if title:
        await conv_svc.aupdate_context_snapshot(cid, {"title": title})
        # 同时更新 conversations 表的 title 字段
        try:
            from app.core.database import get_session_sync
            from app.models.conversation import ConversationModel
            from sqlalchemy import update
            factory = get_session_sync()
            async with factory() as session:
                await session.execute(
                    update(ConversationModel)
                    .where(ConversationModel.conversation_id == cid)
                    .values(title=title)
                )
                await session.commit()
        except Exception:
            pass


async def _compress_and_save(
    cid: str, conv_svc, prev_summary: str,
    last_query: str, last_answer: str, pending_question: str | None,
):
    """后台异步压缩对话历史并写入 context_snapshot。"""
    if not cid or not last_query:
        return
    try:
        from app.services.context_compressor import get_context_compressor
        compressor = get_context_compressor()
        result = await compressor.compress(
            prev_summary=prev_summary,
            last_query=last_query,
            last_answer=last_answer,
            pending_question=pending_question,
        )
        await conv_svc.aupdate_context_snapshot(cid, {
            "conversation_summary": result.get("summary", ""),
        })
    except Exception:
        pass  # 压缩失败不影响主链路


async def _build_recent_turns(cid, conv_svc, current_turn: dict) -> list[dict]:
    """追加当前轮，保留最近 3 轮摘要 (async — 在事件循环中直接 await)。"""
    try:
        snapshot = await conv_svc.get_context_snapshot(cid)
    except Exception:
        snapshot = {}
    turns = snapshot.get("recent_turns", [])
    if not isinstance(turns, list):
        turns = []
    turns.append(current_turn)
    return turns[-3:]


# ============================================================
# 辅助: 写入/读取聚焦商品到 conversation context_snapshot
# ============================================================
async def _write_focus_product(conv_svc, conversation_id: str, product):
    """问豆仔点击时锁定商品 → context_snapshot"""
    if not conv_svc or not conversation_id:
        return
    try:
        await conv_svc.set_focus_product(conversation_id, product)
    except Exception as e:
        logger.warning(f"Failed to write focus_product: {e}")


async def _read_focus_product(conv_svc, conversation_id: str) -> dict:
    """读取聚焦商品, 返回 {id,title,price,brand} 或空dict"""
    if not conv_svc or not conversation_id:
        return {}
    try:
        snapshot = await conv_svc.get_context_snapshot(conversation_id)
        fp = snapshot.get("focus_product", {})
        if fp:
            logger.info(f"Focus product read: {fp.get('product_id')} {fp.get('title','')[:50]}")
        return fp
    except Exception as e:
        logger.warning(f"Failed to read focus_product: {e}")
        return {}


async def _get_address(user_id: str) -> dict | None:
    """获取用户默认地址 — 兼容 PG (async) 和内存 (sync) 两种仓库"""
    if not user_id:
        user_id = DEMO_USER_ID
    try:
        from app.repositories.address_repo import get_address_repo
        repo = get_address_repo()
        if hasattr(repo, "_alist"):
            addrs = await repo._alist(user_id)
        else:
            addrs = repo.list(user_id)
        # 如果用给定 user_id 查不到，兜底查 DEMO_USER_ID（Android 端可能传空字符串）
        if not addrs and user_id != DEMO_USER_ID:
            if hasattr(repo, "_alist"):
                addrs = await repo._alist(DEMO_USER_ID)
            else:
                addrs = repo.list(DEMO_USER_ID)
        return next((a for a in addrs if a.get("is_default")), addrs[0] if addrs else None)
    except Exception as e:
        logger.warning(f"Failed to get address for {user_id}: {e}")
        return None


# ============================================================
# 路由
# ============================================================

@router.post("/stream")
async def recommend_stream(req: StreamRequest, raw_request: Request):

    async def gen() -> AsyncGenerator[str, None]:
        sid = req.session_id or str(_uuid.uuid4())[:8]
        uid = req.user_id or ""
        cid = req.conversation_id or ""
        msg = req.message or ""

        # ---- 判断意图: 购物操作关键词 ----
        order_words = ["下单", "结算", "结账", "买单", "付款"]
        confirm_words = ["确认下单", "确认订单", "确认付款"]
        addr_words = ["修改地址", "改地址", "换地址"]
        clear_words = ["清空购物车"]
        cart_show_words = ["购物车有什么", "看看购物车", "看购物车"]
        cart_remove_words = ["删除第", "去掉第", "移除第"]
        cart_qty_words = ["数量改成", "数量改为", "数量改成第", "数量改为第"]
        cart_add_words = ["加入购物车", "加到购物车", "加进购物车", "加购", "全部加入"]
        all_shop_words = (order_words + confirm_words + addr_words + clear_words
                          + cart_show_words + cart_remove_words + cart_qty_words + cart_add_words)
        is_shop = any(kw in msg for kw in all_shop_words)

        CHINESE_NUM = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10}

        def _parse_ordinal(text: str, prefix: str) -> int | None:
            """从 '删除第二个' 中提取序号 → 2 (1-indexed)。
            支持: 第二个/第2个/二/2 等表达。
            """
            import re
            # 先尝试 "第X" 格式
            m = re.search(r"(?:" + prefix + r")\s*(\d+|[一二三四五六七八九十]+)", text)
            if not m:
                # 再尝试纯数字或中文数字（如 "2个" "二个"）
                m = re.search(r"(\d+)\s*个", text)
                if not m:
                    m = re.search(r"([一二三四五六七八九十])\s*个", text)
            if not m:
                return None
            num_str = m.group(1)
            if num_str is None:
                return None
            if num_str.isdigit():
                return int(num_str)
            return CHINESE_NUM.get(num_str)

        def _parse_qty(text: str) -> int | None:
            """从 '数量改成3' 中提取数字"""
            import re
            m = re.search(r"(\d+)", text)
            return int(m.group(1)) if m else None

        # ---- 初始化 conv_svc ----
        conv_svc = None
        try:
            from app.services.conversation_service import get_conversation_service
            conv_svc = get_conversation_service()
        except Exception as e:
            logger.warning(f"conv_svc init failed: {e}")

        # 读取 pending SKU 选择（用户可能正在选规格）
        _pending_sku = {}
        try:
            if conv_svc and cid:
                snap = await conv_svc.get_context_snapshot(cid)
                _pending_sku = (snap or {}).get("pending_sku_product", {}) or {}
        except Exception:
            pass

        # ================================================================
        # 购物操作流程 (加购 / 购物车管理 / 下单)
        # ================================================================
        if is_shop or _pending_sku:
            # 读取可能的下单来源: focus_product → last_products → cart
            fp = await _read_focus_product(conv_svc, cid)
            fp_id = fp.get("product_id", "")
            fp_title = fp.get("title", "")
            fp_price = float(fp.get("price", 0))
            fp_brand = fp.get("brand", "")

            # 读取上一轮推荐的商品 (供 "第一个下单" 等指代)
            last_products = []
            try:
                snapshot = await conv_svc.get_context_snapshot(cid) if conv_svc and cid else {}
                last_products = snapshot.get("last_products", []) or []
            except Exception:
                pass

            async def _yield_answer(text: str, actions: list | None = None):
                """SSE流式: 先逐字token, 再result, 最后done"""
                for ch in text:
                    yield _sse("token", json.dumps({"text": ch}, ensure_ascii=False))
                    await asyncio.sleep(0.03)
                payload = {"answer": text, "products": [], "decision_results": [],
                           "shop_action": True, "harness_report": {}}
                if actions:
                    payload["actions"] = actions
                yield _sse("result", json.dumps(payload, ensure_ascii=False))
                yield _sse("done", "{}")

            async def _persist_order(order_id: str, user_id: str, items: list, total: float):
                """持久化订单到 PG"""
                try:
                    from app.core.database import get_session_sync
                    from app.models.order import OrderModel
                    from datetime import datetime, timezone
                    factory = get_session_sync()
                    async with factory() as session:
                        order = OrderModel(
                            order_id=order_id, user_id=user_id,
                            items=items, total_price=total,
                            status="pending",
                            created_at=datetime.now(timezone.utc),
                        )
                        session.add(order)
                        await session.commit()
                    logger.info(f"Order persisted: {order_id}")
                except Exception as e:
                    logger.warning(f"Order persist failed ({order_id}): {e}")

            # ---- SKU 规格选择（用户点击规格按钮后触发） ----
            if _pending_sku:
                pid = _pending_sku.get("product_id", "")
                if pid:
                    from app.repositories.product_repo import get_product_repo
                    product = get_product_repo().get_by_id(pid)
                    if product and product.skus:
                        # 尝试用消息文本匹配 SKU
                        best_sku = None
                        best_score = 0
                        for s in product.skus:
                            score = 0
                            props = s.properties or {}
                            for k, v in props.items():
                                if k in msg and v in msg:
                                    score += 2
                                elif v in msg:
                                    score += 1
                            if score > best_score:
                                best_score = score
                                best_sku = s
                        if best_sku and best_score > 0:
                            try:
                                from app.repositories.pg_cart_repo import get_cart_repo
                                from app.schemas.cart import CartItemCreate
                                sku_label = " · ".join(f"{k}:{v}" for k,v in (best_sku.properties or {}).items())
                                price = best_sku.price if best_sku.price > 0 else product.base_price
                                title = _pending_sku.get("title") or product.title
                                brand = _pending_sku.get("brand") or product.brand
                                await get_cart_repo().aadd_item(
                                    CartItemCreate(product_id=pid, sku_id=best_sku.sku_id, quantity=1),
                                    uid, title=title, brand=brand, price=price,
                                    image_url=get_product_repo().resolve_image_url(pid),
                                    sku_label=sku_label,
                                )
                                if conv_svc and cid:
                                    try:
                                        await conv_svc.aupdate_context_snapshot(cid, {"pending_sku_product": None})
                                    except Exception:
                                        pass
                                t = (brand + " " + title)[:50]
                                async for e in _yield_answer(f"✅ 已把「{t}」（{sku_label}）加入购物车～"):
                                    yield e
                            except Exception:
                                async for e in _yield_answer("加购失败，请去商品页面手动操作～"):
                                    yield e
                            return

            # ---- 确认下单 (must be before order_words: "确认下单" contains "下单") ----
            if any(kw in msg for kw in confirm_words) or (msg.strip() == "确认" and len(msg.strip()) <= 3):
                # 尝试三个来源: focus_product → cart selected → last_products top1
                items_to_order = []
                if fp_id:
                    items_to_order = [{"product_id": fp_id, "title": fp_title,
                                       "brand": fp_brand, "price": fp_price, "quantity": 1}]
                if not items_to_order:
                    try:
                        from app.repositories.pg_cart_repo import get_cart_repo
                        cart = (await get_cart_repo().aget_cart(uid))
                        selected = [i for i in cart.items if i.selected]
                        if selected:
                            items_to_order = [{"product_id": i.product_id, "title": i.title,
                                               "brand": i.brand, "price": i.price,
                                               "quantity": i.quantity} for i in selected]
                    except Exception:
                        pass
                if not items_to_order and last_products:
                    p = last_products[0]
                    items_to_order = [{"product_id": p.get("product_id",""), "title": p.get("title",""),
                                       "brand": p.get("brand",""), "price": p.get("price",0), "quantity": 1}]

                if not items_to_order:
                    async for e in _yield_answer("没有找到要下单的商品～"):
                        yield e
                    return
                addr = await _get_address(uid)
                if not addr:
                    async for e in _yield_answer("还没有收货地址～点下方按钮填写后再说「下单」就行！",
                                                 [{"type": "address_form", "label": "填写收货地址"}]):
                        yield e
                    return

                total = sum(it.get("price",0) * it.get("quantity",1) for it in items_to_order)
                oid = f"ORD-{_uuid.uuid4().hex[:8].upper()}"
                await _persist_order(oid, uid, items_to_order, total)

                # 构建商品列表文本
                item_lines = []
                for it in items_to_order:
                    b = it.get("brand","")
                    t = it.get("title","")[:50]
                    q = it.get("quantity", 1)
                    p = it.get("price", 0)
                    item_lines.append(f"  {b} {t} x{q}  ¥{p*q:.0f}")
                items_text = "\n".join(item_lines)
                item_count = len(items_to_order)

                text = (
                    f"🎉 下单成功！\n\n"
                    f"📋 订单号：{oid}\n"
                    f"🛒 共{item_count}件：\n{items_text}\n"
                    f"💰 实付：¥{total:.0f}\n"
                    f"📍 {addr.get('name','')} {addr.get('phone','')}\n"
                    f"   {addr.get('province','')}{addr.get('city','')}"
                    f"{addr.get('district','')} {addr.get('detail','')}\n"
                    f"⏱️ 预计2-3天送达\n\n"
                    f"感谢购买！还有什么需要帮忙的吗？"
                )
                # 结算后清空购物车 (非 focus_product 来源)
                if not fp_id:
                    try:
                        from app.repositories.pg_cart_repo import get_cart_repo
                        await get_cart_repo().aclear_cart(uid)
                    except Exception:
                        pass
                async for e in _yield_answer(text):
                    yield e
                return

            # ---- 购物车: 查看 ----
            if any(kw in msg for kw in cart_show_words):
                try:
                    from app.repositories.pg_cart_repo import get_cart_repo
                    cart = (await get_cart_repo().aget_cart(uid))
                    if not cart.items:
                        async for e in _yield_answer("🛒 购物车还是空的～去逛逛商品吧！"):
                            yield e
                    else:
                        lines = ["🛒 你的购物车："]
                        for idx, it in enumerate(cart.items, 1):
                            b = it.brand or ""
                            t = it.title[:50] if it.title else ""
                            q = it.quantity
                            p = it.price
                            lines.append(f"  {idx}. {b} {t} x{q}  ¥{p*q:.0f}")
                        lines.append(f"\n💰 合计 ¥{cart.total_price:.0f}（{cart.total_count}件）")
                        lines.append("可以对我说「删除第N个」「数量改成N」来管理购物车，说「下单」来结算～")
                        async for e in _yield_answer("\n".join(lines)):
                            yield e
                except Exception:
                    async for e in _yield_answer("暂时无法查看购物车，请去购物车页面查看～"):
                        yield e
                return

            # ---- 购物车: 删除第N个 ----
            if any(kw in msg for kw in cart_remove_words):
                n = _parse_ordinal(msg, r"删除第|去掉第|移除第")
                if n is None:
                    async for e in _yield_answer("请说「删除第几个」哦～比如「删除第二个」"):
                        yield e
                    return
                try:
                    from app.repositories.pg_cart_repo import get_cart_repo
                    cart = (await get_cart_repo().aget_cart(uid))
                    if n < 1 or n > len(cart.items):
                        async for e in _yield_answer(f"购物车只有{len(cart.items)}件商品哦～"):
                            yield e
                        return
                    item = cart.items[n - 1]
                    title = (item.brand + " " + item.title)[:60] if item.title else "商品"
                    cart_repo = get_cart_repo()
                    await cart_repo.aremove_item(item.cart_item_id, uid)
                    async for e in _yield_answer(f"🗑 已删除「{title}」"):
                        yield e
                except Exception as e:
                    logger.warning(f"Cart remove error: {type(e).__name__}: {e}", exc_info=True)
                    async for e in _yield_answer("删除失败，请去购物车页面手动操作～"):
                        yield e
                return

            # ---- 购物车: 修改数量 ----
            if any(kw in msg for kw in cart_qty_words):
                qty = _parse_qty(msg)
                if qty is None or qty < 1:
                    async for e in _yield_answer("请说「数量改成N」哦～比如「数量改成2」"):
                        yield e
                    return
                # 先看有没有指定第N个
                n = _parse_ordinal(msg, r"第")
                try:
                    from app.repositories.pg_cart_repo import get_cart_repo
                    cart = (await get_cart_repo().aget_cart(uid))
                    if not cart.items:
                        async for e in _yield_answer("购物车还是空的～"):
                            yield e
                        return
                    if n is not None:
                        if n < 1 or n > len(cart.items):
                            async for e in _yield_answer(f"购物车只有{len(cart.items)}件商品哦～"):
                                yield e
                            return
                        item = cart.items[n - 1]
                    else:
                        # 没指定序号 → 操作购物车中第一个
                        item = cart.items[0]
                    title = (item.brand + " " + item.title)[:60] if item.title else "商品"
                    cart_repo = get_cart_repo()
                    from app.schemas.cart import CartItemUpdate
                    await cart_repo.aupdate_item(item.cart_item_id, CartItemUpdate(quantity=qty), uid)
                    async for e in _yield_answer(f"🔢 「{title}」数量已改为 {qty}"):
                        yield e
                except Exception:
                    async for e in _yield_answer("修改失败，请去购物车页面手动操作～"):
                        yield e
                return

            # ---- 下单 (触发确认卡片) ----
            if any(kw in msg for kw in order_words):
                items_to_confirm = []
                source_label = ""
                # 来源1: focus_product (问豆仔直接下单)
                if fp_id:
                    items_to_confirm = [{"product_id": fp_id, "title": fp_title,
                                         "brand": fp_brand, "price": fp_price, "quantity": 1}]
                    source_label = "focus"
                # 来源2: 指代上一轮推荐结果 ("第一个下单")
                if not items_to_confirm:
                    n = _parse_ordinal(msg, r"第")
                    if n and last_products and 1 <= n <= len(last_products):
                        p = last_products[n - 1]
                        items_to_confirm = [{"product_id": p.get("product_id",""), "title": p.get("title",""),
                                             "brand": p.get("brand",""), "price": p.get("price",0), "quantity": 1}]
                        source_label = "last"
                # 来源3: 购物车选中商品
                if not items_to_confirm:
                    try:
                        from app.repositories.pg_cart_repo import get_cart_repo
                        cart = (await get_cart_repo().aget_cart(uid))
                        selected = [i for i in cart.items if i.selected]
                        if selected:
                            items_to_confirm = [{"product_id": i.product_id, "title": i.title,
                                                 "brand": i.brand, "price": i.price,
                                                 "quantity": i.quantity} for i in selected]
                            source_label = "cart"
                    except Exception:
                        pass

                if not items_to_confirm:
                    async for e in _yield_answer("请先去浏览商品、加入购物车，或者点「问豆仔」分析后再说「下单」哦～"):
                        yield e
                    return

                total = sum(it.get("price",0) * it.get("quantity",1) for it in items_to_confirm)
                addr = await _get_address(uid)

                # 构建确认卡片
                item_lines = []
                for idx, it in enumerate(items_to_confirm, 1):
                    b = it.get("brand","")
                    t = it.get("title","")[:50]
                    q = it.get("quantity", 1)
                    p = it.get("price", 0)
                    item_lines.append(f"  {idx}. {b} {t}  x{q}  ¥{p*q:.0f}")
                items_text = "\n".join(item_lines)

                addr_str = (
                    f"📍 {addr.get('name','')}  {addr.get('phone','')}\n"
                    f"   {addr.get('province','')}{addr.get('city','')}"
                    f"{addr.get('district','')} {addr.get('detail','')}"
                ) if addr else "📍 未设置收货地址"

                text = (
                    f"📦 订单确认\n\n"
                    f"{items_text}\n\n"
                    f"💰 合计：¥{total:.0f}\n"
                    f"{addr_str}\n\n"
                    + ("确认下单吗？" if addr else "⚠️ 请先设置收货地址～")
                )
                act = (
                    [{"type": "quick_reply", "label": "确认下单"},
                     {"type": "address_form", "label": "修改地址"}]
                    if addr else
                    [{"type": "address_form", "label": "填写收货地址"}]
                )
                # 保存 pending order 到 snapshot，供 "确认" 短回复识别
                if conv_svc and cid and source_label:
                    try:
                        await conv_svc.aupdate_context_snapshot(cid, {
                            "pending_order_items": items_to_confirm,
                        })
                    except Exception:
                        pass
                async for e in _yield_answer(text, act):
                    yield e
                return

            # ---- 修改地址 ----
            if any(kw in msg for kw in addr_words):
                async for e in _yield_answer("好的～在下方填写新地址，填好后告诉我「下单」就行！",
                                             [{"type": "address_form", "label": "填写新地址"}]):
                    yield e
                return

            # ---- 清空购物车 ----
            if any(kw in msg for kw in clear_words):
                try:
                    from app.repositories.pg_cart_repo import get_cart_repo
                    await get_cart_repo().aclear_cart(uid)
                    async for e in _yield_answer("✅ 购物车已清空～"):
                        yield e
                except Exception:
                    async for e in _yield_answer("清空失败，请去购物车页面手动操作～"):
                        yield e
                return

            # ---- 加购 (对话式) ----
            if any(kw in msg for kw in cart_add_words):
                target = None
                # 来源1: focus_product (问豆仔)
                if fp_id:
                    target = {"product_id": fp_id, "title": fp_title, "brand": fp_brand, "price": fp_price}
                # 来源2: 序号指代 ("把第二个加入购物车")
                if not target and last_products:
                    n = _parse_ordinal(msg, r"第")
                    if n and 1 <= n <= len(last_products):
                        p = last_products[n - 1]
                        target = {"product_id": p.get("product_id",""), "title": p.get("title",""),
                                  "brand": p.get("brand",""), "price": p.get("price",0)}
                    elif not n:
                        # 无序号 → "全部加入" 或默认 Top1
                        if "全部" in msg:
                            # 批量加购
                            added = 0
                            for p in last_products[:5]:
                                try:
                                    from app.repositories.pg_cart_repo import get_cart_repo
                                    from app.repositories.product_repo import get_product_repo
                                    from app.schemas.cart import CartItemCreate
                                    cart_repo2 = get_cart_repo()
                                    prod_repo2 = get_product_repo()
                                    prod = prod_repo2.get_by_id(p.get("product_id",""))
                                    await cart_repo2.aadd_item(
                                        CartItemCreate(product_id=p.get("product_id",""), quantity=1),
                                        uid,
                                        title=p.get("title",""), brand=p.get("brand",""),
                                        price=p.get("price",0),
                                        image_url=prod_repo2.resolve_image_url(p.get("product_id","")) if prod else "",
                                        sku_label="",
                                    )
                                    added += 1
                                except Exception:
                                    pass
                            async for e in _yield_answer(f"✅ 已把 {added} 件商品加入购物车～"):
                                yield e
                            return
                        else:
                            p = last_products[0]
                            target = {"product_id": p.get("product_id",""), "title": p.get("title",""),
                                      "brand": p.get("brand",""), "price": p.get("price",0)}
                if not target:
                    async for e in _yield_answer("请先说你想买什么，我再帮你加购哦～"):
                        yield e
                    return
                try:
                    from app.repositories.pg_cart_repo import get_cart_repo
                    from app.repositories.product_repo import get_product_repo
                    from app.schemas.cart import CartItemCreate
                    prod_repo = get_product_repo()
                    product = prod_repo.get_by_id(target["product_id"])
                    if not product:
                        async for e in _yield_answer("找不到这件商品了～"):
                            yield e
                        return

                    # 多规格 → 展示选项让用户选
                    skus = getattr(product, "skus", None) or []
                    if len(skus) > 1:
                        sku_actions = []
                        base = product.base_price or 0
                        for s in skus:
                            props = s.properties or {}
                            # 显示 "容量:30ml 经典装" 格式
                            label_parts = [f"{k}:{v}" for k, v in props.items()]
                            label = " · ".join(label_parts)
                            price = s.price if s.price and s.price > 0 else base
                            label += f" ¥{price:.0f}"
                            sku_actions.append({
                                "type": "sku_option",
                                "label": label,
                                "sku_id": s.sku_id,
                            })
                        # 也加一个"不用选"选项
                        sku_actions.append({
                            "type": "sku_option",
                            "label": "默认规格",
                            "sku_id": "",
                        })
                        # 记住 pending 商品，等用户选规格
                        if conv_svc and cid:
                            try:
                                await conv_svc.aupdate_context_snapshot(cid, {
                                    "pending_sku_product": {
                                        "product_id": target["product_id"],
                                        "title": target.get("title",""),
                                        "brand": target.get("brand",""),
                                        "base_price": target.get("price",0),
                                    }
                                })
                            except Exception:
                                pass
                        t = (target.get("brand","") + " " + target.get("title",""))[:50]
                        async for e in _yield_answer(f"「{t}」有 {len(skus)} 个规格，选哪个？", sku_actions):
                            yield e
                        return

                    # 单规格或无规格 → 直接加购
                    sel_sku = skus[0] if skus else None
                    sku_id = sel_sku.sku_id if sel_sku else ""
                    sku_label = " · ".join(f"{k}:{v}" for k,v in (sel_sku.properties or {}).items()) if sel_sku else ""
                    price = sel_sku.price if sel_sku and sel_sku.price > 0 else target.get("price",0)
                    cart_repo = get_cart_repo()
                    await cart_repo.aadd_item(
                        CartItemCreate(product_id=target["product_id"], sku_id=sku_id, quantity=1),
                        uid,
                        title=target.get("title",""),
                        brand=target.get("brand",""),
                        price=price,
                        image_url=prod_repo.resolve_image_url(target["product_id"]),
                        sku_label=sku_label,
                    )
                    t = (target.get("brand","") + " " + target.get("title",""))[:60]
                    extra = f"（{sku_label}）" if sku_label else ""
                    async for e in _yield_answer(f"✅ 已把「{t}」{extra}加入购物车～"):
                        yield e
                except Exception:
                    async for e in _yield_answer("加购失败，请去商品页面手动操作～"):
                        yield e
                return

            # 兜底
            async for e in _yield_answer("好的～你可以对商品点「问豆仔」后说「下单」来直接结算哦！"):
                yield e
            return

        # ================================================================
        # 以下是原有的推荐/聚焦分析流程 (保持不变)
        # ================================================================
        import time as _time
        _t_total_start = _time.perf_counter()

        is_focused = (
            req.mode == "product_focused_analysis"
            and req.target_product_id
            and req.target_product_id.strip()
        )

        # P0: conversation
        try:
            conv_result = await conv_svc.aget_or_create(
                user_id=uid, session_id=sid, conversation_id=cid,
            )
            cid = conv_result["conversation_id"]
        except Exception:
            pass

        if cid:
            try:
                await conv_svc.aappend_user_message(
                    conversation_id=cid, user_id=uid,
                    session_id=sid, content=req.message,
                    image_url=req.image_url or "",
                )
            except Exception:
                pass

        # P2 + P4: FollowUpEngine + Profile 并行加载
        _t0 = _time.perf_counter()
        enriched_query = req.message
        followup_constraints = {}
        context_prompt = ""

        async def _run_followup():
            nonlocal enriched_query, followup_constraints
            try:
                from app.services.followup_engine import get_followup_engine
                engine = get_followup_engine()
                fu = engine.detect(conversation_id=cid, session_id=sid, current_query=req.message)
                if fu.get("is_follow_up") and fu.get("context_prompt"):
                    enriched_query = f"{req.message}\n\n{fu['context_prompt']}"
                if fu.get("updated_constraints"):
                    followup_constraints = fu["updated_constraints"]
                return fu
            except Exception:
                return {}

        async def _run_profile():
            try:
                if uid:
                    from app.services.user_profile_service import get_user_profile_service
                    return await get_user_profile_service().inject_profile_hints(
                        uid, query=req.message, enriched_query=req.message,
                        context_prompt="",
                    )
            except Exception:
                pass
            return {"enriched_query": req.message, "context_prompt": "", "avoid_tags": []}

        import asyncio as _asyncio
        follow_up, hints_result = await _asyncio.gather(_run_followup(), _run_profile())
        # 合并：FollowUp context_prompt + Profile context_prompt
        context_prompt = (follow_up.get("context_prompt", "") + "\n" + hints_result["context_prompt"]).strip()
        # 如果 FollowUp 改写了 query，保留改写版本；否则用 profile 增强版
        if enriched_query == req.message:
            enriched_query = hints_result["enriched_query"]
        logger.info(f"⏱ followup+profile: {(_time.perf_counter() - _t0)*1000:.0f}ms (parallel)")

        # ⭐ 对话式加购: FollowUpEngine 检测到 cart_intent → 直接加购
        if follow_up.get("follow_up_type") == "cart_intent":
            pid = follow_up.get("cart_intent_product_id", "")
            if pid:
                try:
                    from app.repositories.pg_cart_repo import get_cart_repo
                    from app.repositories.product_repo import get_product_repo
                    from app.schemas.cart import CartItemCreate
                    product = get_product_repo().get_by_id(pid)
                    if product:
                        await get_cart_repo().aadd_item(
                            CartItemCreate(product_id=pid, quantity=1), uid,
                            title=product.title, brand=product.brand,
                            price=product.base_price,
                            image_url=get_product_repo().resolve_image_url(product.product_id),
                            sku_label="",
                        )
                        title_short = (product.brand + " " + product.title)[:60]
                        # SSE 流式输出加购确认
                        answer = f"✅ 已把「{title_short}」加入购物车～"
                        for ch in answer:
                            yield _sse("token", json.dumps({"text": ch}, ensure_ascii=False))
                            await asyncio.sleep(0.03)
                        yield _sse("result", json.dumps({
                            "session_id": sid, "conversation_id": cid,
                            "answer": answer, "products": [], "decision_results": [],
                            "shop_action": True, "harness_report": {},
                        }, ensure_ascii=False))
                        yield _sse("done", json.dumps({"finish_reason": "stop"}))
                        return
                except Exception as e:
                    logger.warning(f"cart_intent add failed: {e}")
                    # 加购失败不阻塞，降级走正常推荐流程

        # P4: 对话提取检查 — 后台执行，不阻塞用户看到回复
        try:
            if uid:
                from app.services.user_profile_service import get_user_profile_service
                _svc = get_user_profile_service()
                if _svc.has_long_term_signal(req.message):
                    asyncio.create_task(_svc.parse_and_merge(uid, req.message))
        except Exception:
            pass

        try:
            target_analysis = None
            alternatives = []
            comparison = None
            cross_category = []

            if is_focused:
                target_pid = req.target_product_id.strip()
                from app.repositories.product_repo import get_product_repo
                repo = get_product_repo()
                target = repo.get_by_id(target_pid)

                if target:
                    # 锁定聚焦商品
                    await _write_focus_product(conv_svc, cid, target)

                    cat = target.category
                    sub = target.sub_category
                    rk = target.rag_knowledge

                    # Layer 1: 深度分析
                    review_summary = ""
                    if rk and rk.user_reviews:
                        ratings = [r.rating for r in rk.user_reviews]
                        avg_r = sum(ratings) / len(ratings)
                        pos = sum(1 for r in ratings if r >= 4)
                        review_summary = f"用户口碑: {avg_r:.1f}/5（{len(ratings)}条评论，{pos}条好评）"

                    faq_summary = ""
                    if rk and rk.official_faq:
                        topics = [f.question[:50] for f in rk.official_faq[:3]]
                        faq_summary = f"FAQ覆盖: {' / '.join(topics)}"

                    sku_summary = ""
                    if target.skus:
                        prices = [s.price for s in target.skus]
                        sku_summary = f"共{len(target.skus)}个规格，价格区间 ¥{min(prices):.0f}-¥{max(prices):.0f}"

                    cat_angles = {
                        "数码电子": "参数配置、兼容性、使用场景",
                        "美妆护肤": "成分功效、适用肤质、性价比",
                        "服饰运动": "材质舒适度、尺码适配、穿搭场景",
                        "食品饮料": "口味特点、健康程度、规格划算度",
                    }
                    angle = cat_angles.get(cat, "优缺点、性价比、是否值得买")

                    search_query = f"{target.title} {target.brand} {cat} {sub}"
                    analysis_prompt = (
                        f"顾客在咨询这款商品，请优先重点介绍它：\n"
                        f"「{target.title}」— {target.brand}，¥{target.base_price}，{cat}/{sub}\n"
                        f"参考信息：{review_summary}。{faq_summary}。{sku_summary}。\n"
                        f"描述：{rk.marketing_description[:300] if rk else ''}\n"
                        f"用户问：{req.message}\n\n"
                        f"回复要求：\n"
                        f"1. 先用1-2句热情推荐这款商品，突出它最大的卖点\n"
                        f"2. 列出2-3个核心优点（结合数据）\n"
                        f"3. 一句话说适用人群\n"
                        f"4. 如果数据中有差评/风险项，必须提醒用户注意\n"
                        f"5. 最后如果检索结果里有同类商品，用一句话提一下作为备选\n"
                        f"重点始终放在顾客问的这款商品上，备选只是捎带提及。控制在200字以内。"
                    )
                    if context_prompt:
                        analysis_prompt = analysis_prompt + "\n\n" + context_prompt

                    from app.schemas.workflow import WorkflowState, Constraints, RetrievalPlan
                    profile_avoid = hints_result.get("avoid_tags") or []
                    prefill = WorkflowState(
                        user_query=search_query,
                        image_url=req.image_url,
                        constraints=Constraints(category=cat, sub_category=sub,
                                                exclude_tags=profile_avoid),
                        retrieval_plan=RetrievalPlan(
                            channels=["text", "review", "policy"],
                            category=cat, sub_category=sub, top_k=5,
                        ),
                    )
                    state = await run_workflow(
                        user_query=search_query,
                        image_url=req.image_url,
                        session_id=sid, user_id=uid,
                        conversation_id=cid,
                        enable_checkpoint=False,
                        prefill_state=prefill,
                        context_prompt=analysis_prompt,
                        fast_mode=req.fast_mode,
                    )

                    # 确保目标商品在检索结果中
                    target_in_results = any(
                        p.get("product_id") == target_pid
                        for p in state.retrieved_products
                    )
                    if not target_in_results:
                        target_dict = {
                            "product_id": target.product_id,
                            "title": target.title,
                            "brand": target.brand,
                            "category": target.category,
                            "sub_category": target.sub_category,
                            "price": target.base_price,
                            "image_urls": [target.image_path] if target.image_path else [],
                            "rag_knowledge": target.rag_knowledge.model_dump() if target.rag_knowledge else {},
                        }
                        state.retrieved_products.insert(0, target_dict)
                        from app.agents.decision_agent import DecisionAgent
                        await DecisionAgent().execute(state)

                    # 聚焦商品得分拉满
                    for dr in state.decision_results:
                        if dr.get("product_id") == target_pid:
                            comp = dr.get("component_scores", {})
                            if "relevance" in comp:
                                comp["relevance"]["score"] = 1.0
                            if "scenario_fit" in comp:
                                comp["scenario_fit"]["score"] = 1.0
                            raw = sum(v["score"] * (v.get("weight") or 0) for v in comp.values())
                            dr["final_score"] = min(1.0, raw)
                            dr["display_score"] = round(raw * 10, 1)
                            dr["recommendation_level"] = "strong_recommend" if raw >= 0.80 else "recommended"
                            break

                    # 构建 target_analysis
                    target_dec = None
                    for dr in state.decision_results:
                        if dr.get("product_id") == target_pid:
                            target_dec = dr
                            break

                    if target_dec:
                        strengths = []
                        if rk and rk.user_reviews:
                            ratings = [r.rating for r in rk.user_reviews]
                            avg_r = sum(ratings) / len(ratings)
                            if avg_r >= 4.0:
                                strengths.append(f"用户口碑好({avg_r:.1f}/5)")
                        if rk and rk.official_faq:
                            strengths.append(f"FAQ覆盖{len(rk.official_faq)}个问题")
                        faq_questions = [f.question for f in rk.official_faq[:5]] if rk and rk.official_faq else []
                        component_scores = target_dec.get("component_scores", {})
                        target_analysis = {
                            "product_id": target_pid,
                            "title": target.title,
                            "brand": target.brand,
                            "price": target.base_price,
                            "category": cat,
                            "sub_category": sub,
                            "recommendation_level": target_dec.get("recommendation_level", ""),
                            "display_score": target_dec.get("display_score", 0),
                            "evidence_confidence": target_dec.get("evidence_confidence", 0),
                            "suitable_for": [s for s in strengths[:3] if s],
                            "strengths": [s for s in strengths[:3] if s],
                            "risks": target_dec.get("risk_factors", [])[:3],
                            "faq_questions": faq_questions,
                            "review_summary": {
                                "count": len(ratings),
                                "avg_rating": round(sum(ratings) / len(ratings), 1) if ratings else 0,
                                "positive_ratio": round(sum(1 for r in ratings if r >= 4) / len(ratings) * 100) if ratings else 0,
                            } if ratings else None,
                            "sku_advice": sku_summary,
                            "component_scores": {k: v for k, v in list(component_scores.items())[:7]},
                            "support_evidence_ids": target_dec.get("support_evidence_ids", []),
                        }

                    # 同类对比 + 场景拓展 (略,保持不变)
                    alt_products = [p for p in state.retrieved_products if p.get("product_id") != target_pid][:3]
                    alt_decisions = [d for d in state.decision_results if d.get("product_id") != target_pid][:3]
                    for ap, ad in zip(alt_products, alt_decisions):
                        alternatives.append({
                            "product_id": ap.get("product_id"),
                            "title": ap.get("title", ""),
                            "brand": ap.get("brand", ""),
                            "price": ap.get("price", 0),
                            "display_score": ad.get("display_score", 0),
                            "recommendation_level": _LEVEL_CN.get(ad.get("recommendation_level", ""), ad.get("recommendation_level", "")),
                        })
                    if target_analysis and alternatives:
                        dims = ["价格", "推荐分", "推荐等级"]
                        tgt_vals = [
                            f"¥{target.base_price:.0f}",
                            f"{target_dec.get('display_score',0)}/10",
                            _LEVEL_CN.get(target_dec.get('recommendation_level',''), target_dec.get('recommendation_level','')),
                        ]
                        alt_rows = []
                        for a in alternatives:
                            alt_rows.append([f"¥{a['price']:.0f}", f"{a['display_score']}/10", a["recommendation_level"]])
                        cs = target_dec.get("component_scores", {})
                        for key, label in [("user_sat","用户口碑"), ("value_score","性价比"), ("spec_quality","规格品质")]:
                            if cs.get(key, {}).get("score", 0) > 0:
                                dims.append(label)
                                tgt_vals.append(f"{cs[key]['score']*10:.1f}/10")
                                for idx, ad in enumerate(alt_decisions):
                                    acs = ad.get("component_scores", {})
                                    if idx < len(alt_rows):
                                        alt_rows[idx].append(f"{acs.get(key,{}).get('score',0)*10:.1f}/10")
                        comparison = {
                            "dimensions": dims,
                            "target_values": tgt_vals,
                            "alternative_values": alt_rows,
                        }

                else:
                    from app.schemas.workflow import WorkflowState as Ws
                    state = Ws(
                        user_query=req.message,
                        answer="抱歉～我没找到这件商品的信息 😅 你可以直接告诉我你想买什么，我帮你推荐！",
                        retrieved_products=[], decision_results=[],
                    )
            else:
                # 构建 prefill (FollowUpEngine 检测到的追问约束)
                _t_wf = _time.perf_counter()
                profile_avoid = hints_result.get("avoid_tags") or []
                prefill = _build_constraint_prefill(followup_constraints, profile_avoid)
                state = await run_workflow(
                    user_query=enriched_query, image_url=req.image_url,
                    session_id=sid, user_id=uid, conversation_id=cid,
                    enable_checkpoint=False, prefill_state=prefill,
                    context_prompt=context_prompt,
                    fast_mode=req.fast_mode,
                )
                logger.info(f"⏱ workflow: {(_time.perf_counter() - _t_wf)*1000:.0f}ms (total: {(_time.perf_counter() - _t_total_start)*1000:.0f}ms)")
                if hasattr(state, 'timing') and state.timing:
                    logger.info(f"⏱ breakdown: {json.dumps(state.timing, ensure_ascii=False, default=str)}")

            answer = state.answer or "抱歉，暂时无法回答您的问题。"

            # P3: 购买意向检测
            if is_focused and target:
                purchase_signals = 1
                positive_words = ["不错", "很好", "可以", "就这个", "买", "下单", "要了", "行", "好"]
                if any(w in req.message for w in positive_words):
                    purchase_signals += 1
                if alternatives:
                    purchase_signals += 1
                if purchase_signals >= 2:
                    answer += f"\n\n看起来你对「{target.title[:20]}」挺满意的～要不要我帮你直接下单？回复「下单」就行！"

            # SSE流式输出
            for i, ch in enumerate(answer):
                if await raw_request.is_disconnected():
                    break
                yield _sse("token", json.dumps({"text": ch}, ensure_ascii=False))
                await asyncio.sleep(0.03)

            result = {
                "session_id": sid,
                "conversation_id": cid,
                "answer": answer,
                "products": _safe_dump(state.retrieved_products or []),
                "decision_results": _safe_dump(state.decision_results or []),
                "evidence_list": _safe_dump(state.evidence_list or []),
                "trace_steps": _safe_dump(state.trace_steps or []),
                "harness_report": _safe_dump(state.harness_report or {}),
                "used_memories": _safe_dump(state.used_memories or []),
                "blocked_memories": _safe_dump(state.blocked_memories or []),
                "memory_trace": _safe_dump(state.memory_trace or {}),
                "needs_clarification": state.needs_clarification,
                "clarification_question": state.clarification_question,
                "clarification_options": _safe_dump(state.clarification_options or []),
                "timing": _safe_dump(state.timing or {}),
                "target_product_analysis": target_analysis,
                "alternative_products": alternatives,
                "comparison_table": comparison,
                "cross_category": cross_category,
            }
            yield _sse("result", json.dumps(result, ensure_ascii=False, default=str))
            yield _sse("done", json.dumps({"finish_reason": "stop"}))

            if cid:
                try:
                    # 结构化商品列表 (供 FollowUpEngine 做指代解析)
                    product_ids = []
                    structured_products = []
                    for p in (state.retrieved_products or [])[:10]:
                        pid = p.get("product_id", "")
                        if pid:
                            product_ids.append(pid)
                            structured_products.append({
                                "product_id": pid,
                                "title": p.get("title", "")[:60],
                                "brand": p.get("brand", ""),
                                "price": p.get("price", 0),
                            })

                    await conv_svc.aappend_assistant_message(
                        conversation_id=cid, user_id=uid,
                        session_id=sid, content=answer,
                        product_refs=product_ids,
                    )

                    # 提取豆仔回复中的问题 (供下一轮 Router 做问答链匹配)
                    pending_question = _extract_question(answer)

                    # 保留最近 N 轮对话摘要
                    recent_turns = await _build_recent_turns(cid, conv_svc, {
                        "user_query": req.message,
                        "assistant_answer": answer[:300],
                        "product_ids": product_ids,
                    })

                    # 持久化 Router 检测到的品类，供下一轮 FollowUpEngine 继承
                    snapshot_update = {
                        "last_query": req.message,
                        "last_answer": answer[-500:] if len(answer) > 500 else answer,
                        "last_products": structured_products,
                        "pending_question": pending_question,
                        "recent_turns": recent_turns,
                    }
                    if hasattr(state, 'constraints') and state.constraints:
                        c = state.constraints
                        cur_turn = {}
                        if c.category:
                            cur_turn["category"] = c.category
                        if c.sub_category:
                            cur_turn["sub_category"] = c.sub_category
                        if c.budget_max:
                            cur_turn["budget_max"] = c.budget_max
                        if c.scenario:
                            cur_turn["scenario"] = c.scenario
                        if cur_turn:
                            snapshot_update["current_turn"] = cur_turn
                    await conv_svc.aupdate_context_snapshot(cid, snapshot_update)

                    # P4: 异步上下文压缩 — 不阻塞 SSE，后台增量更新 conversation_summary
                    try:
                        prev_summary = (conv_svc.get_context_snapshot_sync(cid) or {}).get(
                            "conversation_summary", ""
                        ) or ""
                        asyncio.create_task(
                            _compress_and_save(cid, conv_svc, prev_summary,
                                               req.message, answer, pending_question)
                        )
                        # 首次对话生成标题
                        try:
                            snap = conv_svc.get_context_snapshot_sync(cid) or {}
                            existing_title = snap.get("title", "")
                            if not existing_title:
                                asyncio.create_task(
                                    _generate_title(cid, conv_svc, req.message, answer[:200])
                                )
                        except Exception:
                            pass
                    except Exception:
                        pass
                except Exception:
                    pass

        except asyncio.CancelledError:
            logger.info(f"SSE cancelled: {sid}")
        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield _sse("error", json.dumps({"message": str(e)}))
            yield _sse("done", json.dumps({"finish_reason": "error"}))

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


def _safe_dump(obj):
    """递归转换 Pydantic model / 非标准对象为可 JSON 序列化的 dict"""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _safe_dump(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_dump(v) for v in obj]
    if hasattr(obj, "model_dump"):
        return _safe_dump(obj.model_dump())
    if hasattr(obj, "dict"):
        return _safe_dump(obj.dict())
    return str(obj)


def _build_constraint_prefill(constraints: dict, avoid_tags: list | None = None):
    """将 FollowUpEngine 的 constraints dict + profile avoid_tags 转为 WorkflowState prefill"""
    if not constraints and not avoid_tags:
        return None
    from app.schemas.workflow import WorkflowState, Constraints, RetrievalPlan
    c = constraints or {}
    merged_avoid = list(set((c.get("exclude_tags") or []) + (avoid_tags or [])))
    return WorkflowState(
        constraints=Constraints(
            category=c.get("category"),
            sub_category=c.get("sub_category"),
            budget_max=c.get("budget_max"),
            budget_min=c.get("budget_min"),
            exclude_tags=merged_avoid,
        ),
        retrieval_plan=RetrievalPlan(
            channels=["text", "review", "policy"],
            category=c.get("category"),
            sub_category=c.get("sub_category"),
        ),
    )
