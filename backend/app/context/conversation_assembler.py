"""Single, bounded final-answer context for a shopping conversation.

The database message log remains the source of truth.  A checkpoint is only a
versioned projection that lets the answer model retain the active shopping task
without repeatedly injecting old messages, raw tool outputs or agent scratchpad.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

from app.framework.context import create_token_estimator
from app.repositories.conversation_repo import get_conversation_repo


_BUDGET = 2800
_SECTION_CAPS = {
    "history": 620,
    "checkpoint": 620,
    "recommendations": 760,
    "dossier": 720,
    "evidence": 460,
    "preferences": 180,
    "visual": 160,
}
_estimator = create_token_estimator()


def _clip(text: Any, cap: int) -> str:
    text = str(text or "").strip()
    return text if len(text) <= cap else text[: max(0, cap - 1)] + "…"


def _get(value: Any, name: str, default=None):
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _display_product_name(product: dict[str, Any]) -> str:
    """生成给回答模型用的短商品名，避免把电商营销长标题带进最终表达。

    原始 ``title`` 仍由卡片和详情页完整保留；这里仅是回答上下文的阅读投影。
    保留品牌、型号和核心品类，截去认证、配色、促销和参数尾巴。
    """
    brand = re.sub(r"\s+", " ", str(product.get("brand") or "").strip())
    title = re.sub(r"\s+", " ", str(product.get("title") or "").strip())
    if brand and title.lower().startswith(brand.lower()):
        title = title[len(brand):].lstrip(" -｜|")
    # 常见营销尾巴前截断；未命中时仍保留足够识别型号的 42 个字符。
    marker = re.search(
        r"(?:Hi-Res|金标认证|超长续航|续航\d|蓝牙\d|防水|轻量|限时|官方|新品|送|赠|颜色|配色)",
        title,
        flags=re.IGNORECASE,
    )
    if marker and marker.start() >= 10:
        title = title[:marker.start()].rstrip("，,、 -")
    title = _clip(title, 42)
    return " ".join(part for part in (brand, title) if part).strip()


@dataclass
class AnswerContext:
    text: str
    manifest: dict[str, Any]


class ConversationContextAssembler:
    """Build one context projection shared by standard and deep response paths."""

    async def assemble(self, state) -> AnswerContext:
        checkpoint: dict[str, Any] = {}
        messages: list[Any] = []
        if state.conversation_id:
            repo = get_conversation_repo()
            try:
                checkpoint_model, messages = await asyncio.gather(
                    repo.aget_active_checkpoint(state.conversation_id),
                    repo.alist_messages(state.conversation_id, limit=8),
                )
                if checkpoint_model:
                    checkpoint = {
                        "summary": checkpoint_model.summary,
                        "shopping_state": checkpoint_model.shopping_state or {},
                        "revision": checkpoint_model.revision,
                        "source_through_message_id": checkpoint_model.source_through_message_id or "",
                        "retained_message_ids": checkpoint_model.retained_message_ids or [],
                    }
            except Exception:
                # Migration rollout must not block a response.  The legacy snapshot is
                # used only as a read-compatible projection until the DB is migrated.
                try:
                    from app.services.conversation_service import get_conversation_service
                    snapshot = await get_conversation_service().get_context_snapshot(state.conversation_id)
                    checkpoint = {"summary": snapshot.get("conversation_summary", ""), "shopping_state": snapshot}
                except Exception:
                    pass

        sections: list[tuple[str, str, str]] = []
        sections.append(("current", "[本轮请求]", self._current_request(state)))
        checkpoint_text = self._checkpoint_text(checkpoint)
        if checkpoint_text:
            sections.append(("checkpoint", "[已确认的会话状态]", checkpoint_text))
        history_messages = self._messages_after_checkpoint(messages, checkpoint)
        history_text = self._recent_turns(history_messages, state.user_query)
        if history_text:
            sections.append(("history", "[最近完整对话]", history_text))
        recommendation_text = self._recommendations(state)
        if recommendation_text:
            sections.append(("recommendations", "[本轮可交付商品：只能引用首选]", recommendation_text))
        dossier_text = self._dossier(state)
        if dossier_text:
            sections.append(("dossier", "[已锁定商品的深度档案]", dossier_text))
        evidence_text = self._evidence(state)
        if evidence_text:
            sections.append(("evidence", "[已核对依据]", evidence_text))
        preference_text = self._preferences(state)
        if preference_text:
            sections.append(("preferences", "[与本轮相关的已确认偏好]", preference_text))
        visual_text = self._visual(state)
        if visual_text:
            sections.append(("visual", "[图片识别结果]", visual_text))

        kept_by_key: dict[str, str] = {}
        manifest_sections: list[dict[str, Any]] = []
        used = 0
        # 预算不足时，旧历史和次要证据必须先让位给本轮已锁定的交付内容。
        # 过去直接按展示顺序取 section，620 字的 checkpoint + 两轮历史可能
        # 在 recommendation/dossier 之前耗尽预算，导致回答模型看不到首选卡。
        by_key = {key: (title, body) for key, title, body in sections}
        selection_order = (
            "current", "checkpoint", "recommendations", "dossier", "visual",
            "preferences", "history", "evidence",
        )
        for key in selection_order:
            item = by_key.get(key)
            if not item:
                continue
            title, body = item
            cap = _SECTION_CAPS.get(key, 900)
            body = _clip(body, cap)
            candidate = title + "\n" + body
            tokens = self._tokens(candidate)
            if key != "current" and used + tokens > _BUDGET:
                manifest_sections.append({"section": key, "included": False, "reason": "budget"})
                continue
            kept_by_key[key] = candidate
            used += tokens
            manifest_sections.append({"section": key, "included": True, "tokens": tokens})
        # 向模型呈现时仍维持自然阅读顺序；选择优先级只决定谁在压力下被裁剪。
        text = "\n\n".join(
            kept_by_key[key] for key, _, _ in sections if key in kept_by_key
        )
        manifest = {
            "version": "answer_context_v1", "budget": _BUDGET, "tokens": used,
            "checkpoint_revision": checkpoint.get("revision", 0),
            "sections": manifest_sections,
            "sources": self._sources(state, checkpoint, history_messages),
        }
        state.answer_context = text
        state.answer_context_manifest = manifest
        return AnswerContext(text=text, manifest=manifest)

    @staticmethod
    def _sources(state, checkpoint: dict[str, Any], messages: list[Any]) -> dict[str, Any]:
        """只记录来源标识，供审计定位；不把原始语料再复制进 manifest。"""
        return {
            "current": {"request": "workflow_state.user_query"},
            "checkpoint": {
                "revision": checkpoint.get("revision", 0),
                "source_through_message_id": checkpoint.get("source_through_message_id", ""),
            },
            "history": {"message_ids": [
                str(getattr(message, "message_id", "")) for message in messages[-4:]
                if getattr(message, "message_id", "")
            ]},
            "recommendations": {"primary_product_ids": list(state.primary_product_ids or [])[:3]},
            "dossier": {"product_id": str(getattr(state, "focus_product_id", "") or "")},
            "evidence": {"product_ids": list(state.primary_product_ids or [])[:3]},
            "preferences": {"memory_count": len(state.used_memories or [])},
            "visual": {"has_visual_result": bool(state.visual_result)},
        }

    @staticmethod
    def _messages_after_checkpoint(messages: list[Any], checkpoint: dict[str, Any]) -> list[Any]:
        """Checkpoint 已概括的消息不能再次进入最终模型上下文。"""
        source_id = str(checkpoint.get("source_through_message_id") or "")
        if not source_id:
            return messages
        for index, message in enumerate(messages):
            if str(getattr(message, "message_id", "")) == source_id:
                return messages[index + 1:]
        # 查询窗口可能没有包含 checkpoint 边界；此时所有窗口消息都比该
        # checkpoint 新，保守保留，不能错误清空用户刚发的追问。
        return messages

    @staticmethod
    def _current_request(state) -> str:
        c = state.constraints
        plan = state.retrieval_plan
        bits = [f"用户现在说：{_clip(state.user_query, 360)}"]
        if state.intent:
            bits.append(f"意图：{state.intent}")
        constraints = []
        for label, value in (("品类", c.category), ("子类", c.sub_category), ("预算上限", c.budget_max),
                             ("场景", c.scenario)):
            if value not in (None, "", 0):
                shown = f"{float(value):g}" if label == "预算上限" else value
                constraints.append(f"{label}={shown}{'元' if label == '预算上限' else ''}")
        if c.must_tags:
            constraints.append("必须=" + "、".join(c.must_tags[:6]))
        if c.exclude_tags:
            constraints.append("避开=" + "、".join(c.exclude_tags[:6]))
        if constraints:
            bits.append("本轮约束：" + "；".join(constraints))
        goal = _get(plan, "answer_goal", "")
        if goal:
            bits.append("交付目标：" + _clip(goal, 160))
        if state.needs_clarification:
            bits.append("需要优先澄清：" + _clip(state.clarification_question, 180))
        return "\n".join(bits)

    @staticmethod
    def _checkpoint_text(checkpoint: dict[str, Any]) -> str:
        state = checkpoint.get("shopping_state") or {}
        lines = []
        if checkpoint.get("summary"):
            lines.append(_clip(checkpoint["summary"], 500))
        mapping = (("active_goal", "当前目标"), ("constraints", "已确认约束"),
                   ("focus_product", "锁定商品"), ("last_products", "上轮商品顺序"),
                   ("pending_question", "待确认"), ("topic", "当前主题"))
        for key, label in mapping:
            value = state.get(key)
            if value:
                lines.append(f"{label}：{_clip(value, 220)}")
        return "\n".join(lines)

    @staticmethod
    def _recent_turns(messages: list[Any], current_query: str) -> str:
        # Use only complete user→assistant turns.  The current user message is
        # already represented above and must not be duplicated as a dangling turn.
        filtered = [m for m in messages if not (getattr(m, "role", "") == "user" and getattr(m, "content", "") == current_query)]
        pairs: list[tuple[Any, Any]] = []
        pending = None
        for msg in filtered:
            if getattr(msg, "role", "") == "user":
                pending = msg
            elif getattr(msg, "role", "") == "assistant" and pending is not None:
                pairs.append((pending, msg))
                pending = None
        lines = []
        for user, assistant in pairs[-2:]:
            lines.append("用户：" + _clip(getattr(user, "content", ""), 180))
            lines.append("欧米：" + _clip(getattr(assistant, "content", ""), 240))
        return "\n".join(lines)

    @staticmethod
    def _recommendations(state) -> str:
        product_by_id = {p.get("product_id"): p for p in (state.retrieved_products or []) if p.get("product_id")}
        brief_by_id = {b.get("product_id"): b for b in (state.recommendation_brief or [])}
        role_by_id: dict[str, str] = {}
        for group in state.retrieval_groups or []:
            role = _get(group, "role", "")
            for pid in _get(group, "product_ids", []) or []:
                if pid and role and pid not in role_by_id:
                    role_by_id[str(pid)] = str(role)
        lines = []
        primary_ids = list(state.primary_product_ids or [])[:3]
        if primary_ids:
            lines.append(f"回答覆盖要求：本轮有 {len(primary_ids)} 款首选；必须逐一介绍，不能只写第一款。")
        for pid in primary_ids:
            p, b = product_by_id.get(pid, {}), brief_by_id.get(pid, {})
            if not p:
                continue
            role = role_by_id.get(str(pid)) or p.get("group_role") or ""
            group_prefix = f"[{role}] " if role else ""
            lines.append(
                f"首选 {group_prefix}[{pid}] {_display_product_name(p)}｜¥{p.get('price', 0)}"
                f"｜{b.get('why_it_fits') or p.get('card_reason') or '与本轮需求接近'}"
                f"｜{b.get('caution') or '注意：以商品详情为准'}"
            )
        missing_groups = []
        for group in state.retrieval_groups or []:
            if _get(group, "status", "") not in {"missing", "failed"}:
                continue
            role = _get(group, "role", "该目标") or "该目标"
            reason = _get(group, "missing_reason", "") or "当前条件下未找到合格商品"
            missing_groups.append(f"缺少 [{role}]：{_clip(reason, 120)}。不能把其他分组商品说成它的替代。")
        lines.extend(missing_groups)
        if not lines and not state.retrieved_products:
            return "没有找到合格商品；请诚实说明缺少的条件并建议放宽方向。"
        return "\n".join(lines)

    @staticmethod
    def _evidence(state) -> str:
        allowed = set(state.primary_product_ids or [])
        lines, seen = [], set()
        for e in state.evidence_list or []:
            pid = str(e.get("product_id") or "")
            if pid not in allowed or pid in seen:
                continue
            content = _clip(e.get("content") or e.get("text") or "", 120)
            if content:
                lines.append(f"[{pid}] {content}")
                seen.add(pid)
        return "\n".join(lines)

    @staticmethod
    def _dossier(state) -> str:
        """为单品聚焦回答提供受控档案，而不是把工具原文塞进 context_prompt。"""
        product_id = str(getattr(state, "focus_product_id", "") or "")
        dossier = (getattr(state, "product_dossiers", {}) or {}).get(product_id) or {}
        if not product_id or not dossier:
            return ""
        lines = [
            f"锁定主体 [{product_id}] {dossier.get('brand', '')} {dossier.get('title', '')}｜¥{dossier.get('price', 0)}",
            "证据状态：" + str(dossier.get("evidence_status") or "信息有限"),
        ]
        price_range = dossier.get("price_range") or {}
        skus = dossier.get("skus") or []
        if skus:
            # 不能只给模型一个“价格区间”。当商品标题本身带规格（例如 50g）、
            # 但起售价来自另一个 15g SKU 时，模型很容易把两者错误拼成
            # “50g ¥89”。把每个可售规格和对应价格作为受控事实明确给出。
            sku_lines = []
            for sku in skus[:6]:
                if not isinstance(sku, dict):
                    continue
                properties = sku.get("properties") or {}
                spec = " / ".join(
                    f"{key}:{value}" for key, value in properties.items()
                    if value not in (None, "")
                )
                price = sku.get("price")
                if spec and price not in (None, ""):
                    sku_lines.append(f"{spec}＝¥{price}")
            lines.append(
                f"规格：{len(skus)} 个；价格区间 ¥{price_range.get('min', dossier.get('price', 0))}"
                f"-¥{price_range.get('max', dossier.get('price', 0))}"
            )
            if sku_lines:
                lines.append("可售规格与对应价格：" + "；".join(sku_lines))
                lines.append("规格和价格必须按上述一一对应；不能把标题里的规格与另一规格的起售价拼在一起。")
        description = _clip(dossier.get("marketing_description"), 360)
        if description:
            lines.append("商品说明：" + description)
        review = dossier.get("review_summary") or {}
        if review:
            lines.append(
                f"用户评价概览：{review.get('count', 0)} 条；平均 {review.get('avg_rating', '未知')}/5；"
                f"好评 {review.get('positive_count', 0)}，需留意 {review.get('risk_count', 0)}。"
            )
        faq = dossier.get("official_faq") or []
        if faq:
            lines.append("官方问答：" + "；".join(
                f"{_clip(item.get('question'), 80)}：{_clip(item.get('answer'), 130)}" for item in faq[:3]
            ))
        gaps = dossier.get("information_gaps") or []
        if gaps:
            lines.append("信息缺口：" + "；".join(_clip(item, 90) for item in gaps[:4]))
        lines.append("只分析这件已锁定商品；没有用户明确要求时，不主动推荐替代品或扩展到同类。")
        return "\n".join(lines)

    @staticmethod
    def _preferences(state) -> str:
        return "；".join(_clip(m.get("content", ""), 80) for m in (state.used_memories or [])[:2] if m.get("content"))

    @staticmethod
    def _visual(state) -> str:
        result = state.visual_result or {}
        values = [
            f"{key}={result[key]}"
            for key in ("brand", "product_name", "product_line", "model", "specs", "category", "sub_category", "image_quality", "confidence")
            if result.get(key) not in (None, "", [])
        ]
        resolution = state.product_resolution or {}
        if resolution.get("source") == "visual_catalog":
            values.append(f"目录匹配={resolution.get('match_type', 'no_match')}")
            if resolution.get("label"):
                values.append(f"匹配结论={resolution['label']}")
        return "；".join(values)

    @staticmethod
    def _tokens(text: str) -> int:
        try:
            return int(_estimator.estimate(text))
        except Exception:
            return max(1, len(text) // 2)


_assembler: ConversationContextAssembler | None = None


def get_conversation_context_assembler() -> ConversationContextAssembler:
    global _assembler
    if _assembler is None:
        _assembler = ConversationContextAssembler()
    return _assembler
