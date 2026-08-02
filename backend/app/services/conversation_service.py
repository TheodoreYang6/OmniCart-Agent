"""Memory Lite: ConversationService — 短期上下文的唯一入口。

职责:
- get_or_create: conversation 生命周期管理
- append_user_message / append_assistant_message: 消息写入
- get_context_snapshot: 一次读取全部短期上下文 (constraints + products + query + focus)
- merge_constraints: 话题切换检测 + 约束合并
- set_last_products / set_last_context / set_focus_product: 上下文更新

短期上下文全部存在 conversations.context_snapshot JSONB 中,
内存缓存仅作为 PG 的读缓存, 不是独立数据源。
"""

import logging
import time
from datetime import datetime, timezone

from app.schemas.workflow import Constraints
from app.repositories.conversation_repo import get_conversation_repo

logger = logging.getLogger(__name__)

DEFAULT_SESSION_TTL = 7200  # 2小时


def _utcnow():
    return datetime.now(timezone.utc)


def _now_ts() -> float:
    return time.time()


class ConversationService:
    """短期上下文管理 — 合并了原 PreferenceMemory 的约束累积逻辑。"""

    def __init__(self):
        self._repo = get_conversation_repo()
        # 内存缓存: cid → context_snapshot dict (PG 的读缓存, 不是独立数据源)
        self._snapshot_cache: dict[str, dict] = {}
        self._last_cleanup = time.time()

    # ================================================================
    # Conversation 生命周期
    # ================================================================

    async def aget_or_create(self, user_id: str, session_id: str,
                             conversation_id: str = "",
                             title: str = "") -> dict:
        if conversation_id:
            existing = await self._repo.aget(conversation_id)
            if existing:
                return {"conversation_id": existing.conversation_id, "is_new": False}
        # P0-1 会话连续性：cid 缺失时按 session_id 复用最近会话
        # （不回传 cid 的客户端否则每轮新建会话，上下文/追问全部丢失）
        if session_id:
            try:
                recent = await self._repo.aget_latest_by_session(user_id, session_id)
            except Exception:  # noqa: BLE001 — 复用失败不阻断，降级新建
                recent = None
            if recent:
                return {"conversation_id": recent.conversation_id, "is_new": False}
        conv = await self._repo.acreate(user_id=user_id, session_id=session_id, title=title)
        return {"conversation_id": conv.conversation_id, "is_new": True}

    def get_or_create(self, user_id: str, session_id: str,
                      conversation_id: str = "", title: str = "") -> dict:
        if conversation_id:
            existing = self._repo.get(conversation_id)
            if existing:
                return {"conversation_id": existing.conversation_id, "is_new": False}
        if session_id:
            try:
                recent = self._repo.get_latest_by_session(user_id, session_id)
            except Exception:  # noqa: BLE001
                recent = None
            if recent:
                return {"conversation_id": recent.conversation_id, "is_new": False}
        conv = self._repo.create(user_id=user_id, session_id=session_id, title=title)
        return {"conversation_id": conv.conversation_id, "is_new": True}

    # ================================================================
    # 消息写入
    # ================================================================

    async def aappend_user_message(self, conversation_id: str, user_id: str,
                                   session_id: str, content: str,
                                   image_url: str = "", metadata: dict | None = None) -> dict:
        msg = await self._repo.aappend_message(
            conversation_id=conversation_id, user_id=user_id,
            session_id=session_id, role="user", content=content,
            image_url=image_url or None, metadata=metadata or {},
        )
        preview = content[:100] if content else ""
        await self._repo.aupdate(conversation_id, last_message=preview)
        return {"message_id": msg.message_id, "role": "user", "content": content[:200]}

    async def aappend_assistant_message(self, conversation_id: str, user_id: str,
                                        session_id: str, content: str,
                                        product_refs: list | None = None,
                                        evidence_refs: list | None = None,
                                        metadata: dict | None = None) -> dict:
        msg = await self._repo.aappend_message(
            conversation_id=conversation_id, user_id=user_id,
            session_id=session_id, role="assistant", content=content,
            product_refs=product_refs or [],
            evidence_refs=evidence_refs or [],
            memory_refs=[], metadata=metadata or {},
        )
        preview = content[:100] if content else ""
        await self._repo.aupdate(conversation_id, last_message=preview)
        return {"message_id": msg.message_id, "role": "assistant", "content": content[:200]}

    # Sync wrappers
    def append_user_message(self, conversation_id: str, user_id: str,
                            session_id: str, content: str,
                            image_url: str = "", metadata: dict | None = None) -> dict:
        msg = self._repo.append_message(
            conversation_id=conversation_id, user_id=user_id,
            session_id=session_id, role="user", content=content,
            image_url=image_url or None, metadata=metadata or {},
        )
        preview = content[:100] if content else ""
        self._repo.aupdate_sync(conversation_id, last_message=preview)
        return {"message_id": msg.message_id, "role": "user", "content": content[:200]}

    def append_assistant_message(self, conversation_id: str, user_id: str,
                                 session_id: str, content: str,
                                 product_refs: list | None = None,
                                 evidence_refs: list | None = None,
                                 metadata: dict | None = None) -> dict:
        msg = self._repo.append_message(
            conversation_id=conversation_id, user_id=user_id,
            session_id=session_id, role="assistant", content=content,
            product_refs=product_refs or [],
            evidence_refs=evidence_refs or [],
            memory_refs=[], metadata=metadata or {},
        )
        preview = content[:100] if content else ""
        self._repo.aupdate_sync(conversation_id, last_message=preview)
        return {"message_id": msg.message_id, "role": "assistant", "content": content[:200]}

    # ================================================================
    # 短期上下文读写 (Memory Lite 核心)
    # ================================================================

    async def get_context_snapshot(self, conversation_id: str) -> dict:
        """一次读取全部短期上下文。先查缓存，缓存未命中则读 PG。

        Returns:
            {
                "constraints": {category, sub_category, budget_max, budget_min, scenario, must_tags, exclude_tags},
                "current_turn": {category, sub_category, ...},  # 本轮 Router 原始提取
                "last_products": ["P001", "P003", ...],
                "last_query": "推荐一款降噪耳机",
                "last_intent": "recommend",
                "focus_product": {product_id, title, price, brand, ...},
            }
        """
        if conversation_id in self._snapshot_cache:
            return self._snapshot_cache[conversation_id]

        conv = await self._repo.aget(conversation_id)
        snapshot = dict(conv.context_snapshot) if conv and conv.context_snapshot else {}
        self._snapshot_cache[conversation_id] = snapshot
        return snapshot

    def get_context_snapshot_sync(self, conversation_id: str) -> dict:
        """同步版 — 仅查 PG (无缓存), 供 FollowUpEngine 等同步调用方使用。"""
        conv = self._repo.get(conversation_id)
        return dict(conv.context_snapshot) if conv and conv.context_snapshot else {}

    async def merge_constraints(self, conversation_id: str,
                                new_constraints: Constraints) -> Constraints:
        """本轮约束合并已累积约束，返回合并后的 Constraints。

        规则:
        - current_turn (本轮 Router 提取) 覆盖 accumulated (累积)
        - category 变化 → 话题切换, 清空旧约束
        - budget_max=0 不是有效值, 不覆盖
        - 合并结果写回 context_snapshot + 缓存
        """
        self._maybe_cleanup()
        snapshot = await self.get_context_snapshot(conversation_id)

        acc = snapshot.get("constraints", {})
        cur = self._build_current_turn(new_constraints)

        # 话题切换检测
        new_cat = cur.get("category")
        old_cat = acc.get("category")
        if new_cat and old_cat and new_cat != old_cat:
            acc = {}
            snapshot["constraints"] = {}
            snapshot["current_turn"] = {}

        # 新查询没检测到品类但旧约束有 → 移除旧品类
        if not new_cat and old_cat:
            acc = {k: v for k, v in acc.items() if k != "category"}

        # 合并: 本轮 > 累积
        merged_acc = dict(acc)
        for key in ("category", "sub_category", "scenario"):
            if cur.get(key):
                merged_acc[key] = cur[key]
        for key in ("budget_max", "budget_min"):
            val = cur.get(key)
            if val is not None and val > 0:
                merged_acc[key] = val
        merged_acc["must_tags"] = list(set(cur.get("must_tags", []) + acc.get("must_tags", [])))
        merged_acc["exclude_tags"] = list(set(cur.get("exclude_tags", []) + acc.get("exclude_tags", [])))

        # 写回
        snapshot["constraints"] = merged_acc
        snapshot["current_turn"] = cur
        snapshot["_updated_at"] = _now_ts()
        self._snapshot_cache[conversation_id] = snapshot
        await self._persist_snapshot(conversation_id, snapshot)

        # 返回合并后的 Constraints
        c = Constraints()
        c.category = cur.get("category") or merged_acc.get("category")
        c.sub_category = cur.get("sub_category") or merged_acc.get("sub_category")
        c.budget_max = cur.get("budget_max") if cur.get("budget_max") is not None and cur.get("budget_max") > 0 else merged_acc.get("budget_max")
        c.budget_min = cur.get("budget_min") if cur.get("budget_min") is not None and cur.get("budget_min") > 0 else merged_acc.get("budget_min")
        c.scenario = cur.get("scenario") or merged_acc.get("scenario")
        c.must_tags = merged_acc.get("must_tags", [])
        c.exclude_tags = merged_acc.get("exclude_tags", [])
        return c

    async def set_last_products(self, conversation_id: str, product_ids: list[str]):
        """记录本轮推荐的商品 ID 列表 (供 FollowUpEngine 做序数引用)。"""
        snapshot = await self.get_context_snapshot(conversation_id)
        snapshot["last_products"] = product_ids[:10]
        snapshot["_updated_at"] = _now_ts()
        self._snapshot_cache[conversation_id] = snapshot
        await self._persist_snapshot(conversation_id, snapshot)

    async def set_last_context(self, conversation_id: str, query: str = "", intent: str = ""):
        """记录本轮查询上下文 (供 Router LLM 下一轮注入 prompt)。"""
        snapshot = await self.get_context_snapshot(conversation_id)
        if query:
            snapshot["last_query"] = query
        if intent:
            snapshot["last_intent"] = intent
        snapshot["_updated_at"] = _now_ts()
        self._snapshot_cache[conversation_id] = snapshot
        await self._persist_snapshot(conversation_id, snapshot)

    async def set_focus_product(self, conversation_id: str, product):
        """锁定聚焦商品 (问欧米功能)。"""
        snapshot = await self.get_context_snapshot(conversation_id)
        snapshot["focus_product"] = {
            "product_id": product.product_id,
            "title": product.title,
            "brand": product.brand,
            "category": product.category,
            "sub_category": product.sub_category,
            "price": product.base_price,
            "locked_at": datetime.now(timezone.utc).isoformat(),
        }
        self._snapshot_cache[conversation_id] = snapshot
        await self._persist_snapshot(conversation_id, snapshot)
        logger.info(f"Focus product set: {product.product_id} {product.title[:30]}")

    # ---- 兼容旧接口 ----

    async def aupdate_context_snapshot(self, conversation_id: str, snapshot_update: dict) -> None:
        """合并更新 context_snapshot (兼容旧调用方)。"""
        snapshot = await self.get_context_snapshot(conversation_id)
        snapshot.update(snapshot_update)
        self._snapshot_cache[conversation_id] = snapshot
        await self._persist_snapshot(conversation_id, snapshot)

    def update_context_snapshot(self, conversation_id: str, snapshot_update: dict) -> None:
        conv = self._repo.get(conversation_id)
        if not conv:
            return
        existing = dict(conv.context_snapshot or {})
        existing.update(snapshot_update)
        self._repo.aupdate_sync(conversation_id, context_snapshot=existing)

    # ---- 兼容旧 PreferenceMemory API (供 sync 调用方过渡) ----

    def get_context(self, conversation_id: str, limit: int = 6) -> dict:
        """获取会话上下文 (兼容旧 FollowUpEngine 调用)。"""
        conv = self._repo.get(conversation_id)
        messages = self._repo.list_messages(conversation_id, limit=limit)
        snapshot = dict(conv.context_snapshot) if conv and conv.context_snapshot else {}
        return {
            "conversation_id": conversation_id,
            "context_snapshot": snapshot,
            "recent_messages": [
                {
                    "role": m.role,
                    "content": m.content[:300],
                    "product_refs": m.product_refs or [],
                    "created_at": m.created_at.isoformat() if m.created_at else "",
                }
                for m in messages
            ],
        }

    async def aget_context(self, conversation_id: str, limit: int = 6) -> dict:
        """Async: 获取会话上下文 (兼容旧 agent_stream 调用)。"""
        conv = await self._repo.aget(conversation_id)
        messages = await self._repo.alist_messages(conversation_id, limit=limit)
        snapshot = dict(conv.context_snapshot) if conv and conv.context_snapshot else {}
        return {
            "conversation_id": conversation_id,
            "context_snapshot": snapshot,
            "recent_messages": [
                {
                    "role": m.role,
                    "content": m.content[:300],
                    "product_refs": m.product_refs or [],
                    "created_at": m.created_at.isoformat() if m.created_at else "",
                }
                for m in messages
            ],
        }

    # ---- 历史列表 ----

    def list_user_conversations(self, user_id: str, limit: int = 20) -> list[dict]:
        if not user_id:
            return []
        convs = self._repo.list_by_user(user_id, limit=limit)
        return [
            {
                "conversation_id": c.conversation_id,
                "session_id": c.session_id,
                "title": c.title or "",
                "status": c.status or "active",
                "last_message": c.last_message or "",
                "created_at": c.created_at.isoformat() if c.created_at else "",
                "updated_at": c.updated_at.isoformat() if c.updated_at else "",
            }
            for c in convs
        ]

    def get_messages(self, conversation_id: str, limit: int = 50) -> list[dict]:
        messages = self._repo.list_messages(conversation_id, limit=limit)
        return [
            {
                "message_id": m.message_id,
                "role": m.role,
                "content": m.content,
                "image_url": m.image_url or "",
                "product_refs": m.product_refs or [],
                "evidence_refs": m.evidence_refs or [],
                "created_at": m.created_at.isoformat() if m.created_at else "",
            }
            for m in messages
        ]

    # ================================================================
    # Internal
    # ================================================================

    async def _persist_snapshot(self, conversation_id: str, snapshot: dict):
        """将缓存中的 snapshot 持久化到 PG (best-effort)。"""
        try:
            # 清理内部字段, 只持久化业务数据
            clean = {k: v for k, v in snapshot.items() if not k.startswith("_")}
            await self._repo.aupdate(conversation_id, context_snapshot=clean)
        except Exception as e:
            logger.debug(f"Snapshot persist skipped: {e}")

    def _build_current_turn(self, c: Constraints) -> dict:
        """从 Constraints 提取本轮非空字段。"""
        cur = {}
        if c.category:
            cur["category"] = c.category
        if c.sub_category:
            cur["sub_category"] = c.sub_category
        if c.budget_max is not None and c.budget_max > 0:
            cur["budget_max"] = c.budget_max
        if c.budget_min is not None and c.budget_min > 0:
            cur["budget_min"] = c.budget_min
        if c.scenario:
            cur["scenario"] = c.scenario
        if c.must_tags:
            cur["must_tags"] = c.must_tags
        if c.exclude_tags:
            cur["exclude_tags"] = c.exclude_tags
        return cur

    def _maybe_cleanup(self):
        """每 5 分钟清理一次 TTL 过期的缓存条目 (只清缓存, 不影响 PG)。"""
        now = time.time()
        if now - self._last_cleanup < 300:
            return
        self._last_cleanup = now
        expired = []
        for cid, snap in self._snapshot_cache.items():
            updated = snap.get("_updated_at", 0)
            if now - updated > DEFAULT_SESSION_TTL:
                expired.append(cid)
        for cid in expired:
            self._snapshot_cache.pop(cid, None)


# ---- Singleton ----

_svc: ConversationService | None = None


def get_conversation_service() -> ConversationService:
    global _svc
    if _svc is None:
        _svc = ConversationService()
    return _svc


# ---- Sync compatibility (给 ConversationRepository 补同步封装) ----

def _add_aupdate_sync_to_repo():
    from app.repositories.conversation_repo import ConversationRepository

    def aupdate_sync(self, conversation_id: str, **kwargs):
        from app.core.database import run_async
        return run_async(self.aupdate(conversation_id, **kwargs))

    if not hasattr(ConversationRepository, 'aupdate_sync'):
        ConversationRepository.aupdate_sync = aupdate_sync


_add_aupdate_sync_to_repo()
