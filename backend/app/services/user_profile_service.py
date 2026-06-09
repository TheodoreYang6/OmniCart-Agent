"""UserProfileService — 长期偏好画像业务层（条目化 V2）。

每条偏好是独立条目 (entry_id)，按 category 索引检索。
用户说"推荐手机" → 只匹配 category=数码电子 的条目注入 prompt。
用户说"推荐护肤品" → 只匹配 category=美妆护肤 的条目。
"""

import json
import re
import logging

from app.repositories.user_preference_repo import get_user_preference_repo

_log = logging.getLogger(__name__)

_LONG_TERM_SIGNALS = [
    "记住", "以后都", "我一直", "永远", "长期",
    "保存偏好", "以后就", "一直用", "一直喜欢", "一直买",
]
_TEMPORARY_SIGNALS = ["这次", "本轮", "当前", "暂时", "临时", "先"]

# sub_category → category 映射（Qwen 解析结果自动补全用）
_SUB_TO_CATEGORY = {
    "手机": "数码电子", "电脑": "数码电子", "耳机": "数码电子",
    "充电宝": "数码电子", "平板": "数码电子", "手表": "数码电子",
    "相机": "数码电子", "音箱": "数码电子", "键盘": "数码电子", "鼠标": "数码电子",
    "护肤品": "美妆护肤", "彩妆": "美妆护肤", "洗发水": "美妆护肤",
    "沐浴露": "美妆护肤", "面膜": "美妆护肤", "防晒": "美妆护肤",
    "精华": "美妆护肤", "面霜": "美妆护肤", "粉底": "美妆护肤",
    "灯具": "家居生活", "收纳": "家居生活", "清洁": "家居生活",
    "上衣": "服饰运动", "裤子": "服饰运动", "鞋": "服饰运动",
    "零食": "食品饮料", "饮料": "食品饮料", "茶叶": "食品饮料",
    "跑步": "运动户外", "露营": "运动户外", "骑行": "运动户外", "健身": "运动户外",
}

# 品类关键词 → category 快速检测（用于 inject 时从 query 推断品类）
_CATEGORY_KEYWORDS = {
    "数码电子": ["手机", "电脑", "笔记本", "耳机", "充电宝", "平板", "手表", "相机", "音箱",
                "键盘", "鼠标", "显示器", "数据线", "充电器", "ipad", "iphone", "macbook"],
    "美妆护肤": ["护肤", "化妆", "洗面奶", "面膜", "防晒", "精华", "粉底", "口红", "香水",
                "卸妆", "沐浴露", "洗发", "护发", "爽肤水", "面霜", "眼影", "遮瑕"],
    "家居生活": ["灯具", "收纳", "清洁", "床上", "厨房", "抱枕", "地毯", "窗帘", "拖把"],
    "服饰运动": ["上衣", "裤子", "裙子", "鞋", "包", "配饰", "帽子", "围巾", "袜子", "T恤",
                "衣服", "运动", "健身", "跑步", "瑜伽", "羽绒服", "冲锋衣", "卫衣", "短裤", "长裤", "衬衫"],
    "食品饮料": ["零食", "饮料", "茶叶", "咖啡", "牛奶", "坚果", "饼干", "巧克力",
                "吃的", "食物", "面包", "蛋糕", "方便面", "泡面", "辣条", "薯片", "可乐", "矿泉水"],
    "运动户外": ["跑步", "健身", "瑜伽", "露营", "骑行", "游泳", "登山", "跳绳", "哑铃"],
}


class UserProfileService:

    # ================================================================
    # 品类检测（从 query 快速推断品类，无需调 LLM）
    # ================================================================

    @staticmethod
    def detect_category_from_query(query: str) -> str:
        """从 query 文本快速检测品类，返回品类名或空字符串。"""
        for cat, keywords in _CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in query:
                    return cat
        return ""

    # ================================================================
    # 读取（条目列表）
    # ================================================================

    async def list_entries(self, user_id: str, category: str = "") -> list[dict]:
        """获取用户偏好条目列表。category 为空则返回全部品类。"""
        if not user_id:
            return []
        repo = get_user_preference_repo()
        entries = await repo.alist_by_category(user_id, category)
        return [e.to_dict() for e in entries]

    async def list_all_entries(self, user_id: str) -> list[dict]:
        """获取全部条目（含禁用），供管理界面使用。"""
        if not user_id:
            return []
        repo = get_user_preference_repo()
        return repo.list_all(user_id)

    # ================================================================
    # 一键注入（供 V0/V2/Guide 端点复用，品类感知）
    # ================================================================

    async def inject_profile_hints(
        self, user_id: str, query: str, enriched_query: str = "", context_prompt: str = "",
    ) -> dict:
        """加载与 query 品类匹配的偏好条目，构建 hints。

        query: 用户原始输入（用于品类检测）
        enriched_query: 已追加 FollowUp 上下文的查询（search_hints 追加到此）
        context_prompt: 已有上下文（profile context 追加到此）

        品类匹配逻辑:
          1. 从 query 检测品类关键词
          2. 查询该品类的偏好条目
          3. 如未检测到品类，回退到全部条目（保守策略）
        返回 {"enriched_query": str, "context_prompt": str, "avoid_tags": list[str]}。
        """
        result = {
            "enriched_query": enriched_query or query,
            "context_prompt": context_prompt,
            "avoid_tags": [],
        }
        if not user_id:
            return result

        try:
            category = self.detect_category_from_query(query)
            if not category:
                # 没检测到品类 → 不注入任何偏好，避免污染无关品类的搜索
                return result

            entries = await self.list_entries(user_id, category)
            if not entries:
                # 该品类无偏好条目 → 不注入，不 fallback 到其他品类
                return result

            hints = self._build_search_hints_from_entries(entries)
            if hints:
                result["enriched_query"] = f"{enriched_query or query} {hints}"
            ctx = self._build_context_hints_from_entries(entries, category)
            if ctx:
                result["context_prompt"] = (context_prompt + "\n" + ctx).strip()
            result["avoid_tags"] = self._get_avoid_keywords_from_entries(entries)
        except Exception:
            pass
        return result

    # ================================================================
    # 解析 + 保存（每次创建新条目，不合并）
    # ================================================================

    async def parse_only(self, user_id: str, raw_text: str) -> dict | None:
        """仅解析 raw_text，不写入数据库。供 Android 预览使用。"""
        if not raw_text or not raw_text.strip():
            return None
        parsed = await self._parse_with_qwen(raw_text.strip())
        if parsed is None:
            return None
        parsed = self._normalize_fields(parsed)
        if not parsed.get("category"):
            return None
        return parsed

    async def parse_and_save(self, user_id: str, raw_text: str,
                             entry_id: str = "") -> dict | None:
        """解析 raw_text 并保存为一条新条目。entry_id 非空则覆盖旧条目。"""
        if not user_id or not raw_text or not raw_text.strip():
            return None

        parsed = await self._parse_with_qwen(raw_text.strip())
        if parsed is None:
            return None

        parsed = self._normalize_fields(parsed)
        if not parsed.get("category"):
            return None

        repo = get_user_preference_repo()
        entry = await repo.asave(user_id, raw_text.strip(), parsed, entry_id)
        return entry.to_dict()

    # ---- 对话提取信号检测 ----

    def has_long_term_signal(self, message: str) -> bool:
        if not message or len(message) < 5:
            return False
        has_signal = any(s in message for s in _LONG_TERM_SIGNALS)
        has_temp = any(s in message for s in _TEMPORARY_SIGNALS)
        return has_signal and not has_temp

    # ================================================================
    # 条目 → hints 构建（内部）
    # ================================================================

    @staticmethod
    def _build_search_hints_from_entries(entries: list[dict]) -> str:
        """从多条条目提取检索关键词（must_tags + 品牌名）。

        注意: avoid_tags 不放入搜索词（避免"不要小米"反而召回小米）。
        must_tags 中的品类通用词（如"手机""衣服"）可能跨品类污染，
        只在当前约束品类与偏好品类一致时才加入。
        """
        keywords: set[str] = set()
        for e in entries:
            for tag in (e.get("must_tags") or []):
                tag = tag.replace("肤质适用", "").replace("发质适用", "").strip()
                if tag:
                    keywords.add(tag)
            for brand in (e.get("brands") or []):
                if brand:
                    keywords.add(brand)
        return " ".join(sorted(keywords)) if keywords else ""

    @staticmethod
    def _build_context_hints_from_entries(entries: list[dict], matched_category: str = "") -> str:
        """从多条条目构建偏好上下文 prompt。

        策略:
        - 匹配到品类时：只注入该品类条目的品牌/预算/避雷
        - 未匹配时：所有条目合并，但控制总量
        """
        if not entries:
            return ""

        brands: set[str] = set()
        scenarios: set[str] = set()
        must_tags: set[str] = set()
        avoid_tags: set[str] = set()
        budget_min = None
        budget_max = None

        for e in entries:
            for b in (e.get("brands") or []):
                brands.add(b)
            for s in (e.get("scenarios") or []):
                scenarios.add(s)
            for t in (e.get("must_tags") or []):
                must_tags.add(t)
            for a in (e.get("avoid_tags") or []):
                avoid_tags.add(a)
            if e.get("budget_min") and (budget_min is None or e["budget_min"] < budget_min):
                budget_min = e["budget_min"]
            if e.get("budget_max") and (budget_max is None or e["budget_max"] > budget_max):
                budget_max = e["budget_max"]

        parts = []
        if matched_category:
            parts.append(f"品类: {matched_category}")
        if brands:
            parts.append(f"偏好品牌: {', '.join(sorted(brands))}")
        if scenarios:
            parts.append(f"场景: {', '.join(sorted(scenarios))}")
        if must_tags:
            parts.append(f"偏好: {', '.join(sorted(must_tags))}")
        if avoid_tags:
            parts.append(f"避雷: {', '.join(sorted(avoid_tags))}")
        if budget_min or budget_max:
            lo = f"{budget_min:.0f}" if budget_min else ""
            hi = f"{budget_max:.0f}" if budget_max else ""
            parts.append(f"预算: {lo}~{hi}元")
        if not parts:
            return ""
        note = "优先推荐偏好品牌，但如其他品牌更匹配当前需求也可推荐"
        return "[用户偏好] " + " | ".join(parts) + " | " + note

    @staticmethod
    def _get_avoid_keywords_from_entries(entries: list[dict]) -> list[str]:
        tags: set[str] = set()
        for e in entries:
            for t in (e.get("avoid_tags") or []):
                tags.add(t)
        return sorted(tags)

    # ================================================================
    # 兼容旧 API（供存量代码过渡，内部映射到条目系统）
    # ================================================================

    # 保留旧方法签名供存量代码调用
    def build_search_hints(self, profile: dict) -> str:
        return self._build_search_hints_from_entries([profile])

    def build_context_hints(self, profile: dict) -> str:
        return self._build_context_hints_from_entries([profile])

    def get_avoid_keywords(self, profile: dict) -> list[str]:
        return self._get_avoid_keywords_from_entries([profile])

    # ================================================================
    # 规范化 LLM 返回的未知字段
    # ================================================================

    def _normalize_fields(self, parsed: dict) -> dict:
        """将 Qwen 返回的非标字段映射到 schema，并确保 category 字段存在。"""
        known = {"category", "categories", "sub_categories", "brands", "devices",
                 "scenarios", "avoid_tags", "must_tags", "budget_min", "budget_max"}

        # 统一 categories → category (取第一个)
        cats = parsed.pop("categories", None) or []
        if cats and not parsed.get("category"):
            parsed["category"] = cats[0] if isinstance(cats, list) else str(cats)

        # 统一 sub_categories → sub_category
        subs = parsed.pop("sub_categories", None) or []
        if subs and not parsed.get("sub_category"):
            parsed["sub_category"] = subs[0] if isinstance(subs, list) else str(subs)

        # 皮肤类型 → must_tags
        skin = parsed.pop("skin_type", None) or parsed.pop("skin_types", None)
        if skin:
            if isinstance(skin, str):
                skin = [skin]
            parsed.setdefault("must_tags", [])
            for s in skin:
                tag = f"{s}肤质适用" if "适用" not in s else s
                if tag not in parsed["must_tags"]:
                    parsed["must_tags"].append(tag)
            if not parsed.get("category"):
                parsed["category"] = "美妆护肤"
            if not parsed.get("sub_category"):
                parsed["sub_category"] = "护肤品"

        # 发质 → must_tags
        hair = parsed.pop("hair_type", None)
        if hair:
            parsed.setdefault("must_tags", [])
            for h in ([hair] if isinstance(hair, str) else hair):
                tag = f"{h}发质适用"
                if tag not in parsed["must_tags"]:
                    parsed["must_tags"].append(tag)

        # 不在 known 的字段 → must_tags 或 avoid_tags
        for k, v in list(parsed.items()):
            if k in known or not v:
                continue
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, str):
                        if any(neg in item for neg in ["不", "讨厌", "避免", "敏感"]):
                            parsed.setdefault("avoid_tags", []).append(str(item))
                        else:
                            parsed.setdefault("must_tags", []).append(str(item))
            elif isinstance(v, str):
                parsed.setdefault("must_tags", []).append(v)
            del parsed[k]

        # 从 sub_category 反推 category
        sub = parsed.get("sub_category", "")
        if sub and not parsed.get("category"):
            cat = _SUB_TO_CATEGORY.get(sub)
            if cat:
                parsed["category"] = cat

        return parsed

    # ---- 内部：Qwen 解析 ----

    async def _parse_with_qwen(self, raw_text: str) -> dict | None:
        system = (
            "你是一个购物偏好解析器。从用户输入中提取网购偏好，输出 JSON。\n\n"
            "规则：\n"
            "1. 只提取明确提到的内容，绝对不推测\n"
            "2. categories 字段填写大类（数码电子/美妆护肤/家居生活/服饰运动/食品饮料/运动户外）\n"
            "3. sub_categories 填写小类（手机/电脑/耳机/护肤品/面膜/洗发水...）\n"
            "4. 肤质/发质放入 skin_type 或 hair_type\n"
            "5. '不喜欢/讨厌/怕/别给我'后面的内容放入 avoid_tags\n"
            "6. '喜欢/偏好/想要/必须'后面的特性放入 must_tags\n"
            "7. 空值用 [] 或 null，只输出 JSON\n\n"
            "示例：\n"
            "- '喜欢苹果手机预算500' → {categories:['数码电子'],sub_categories:['手机'],brands:['Apple'],devices:['iPhone'],budget_max:500}\n"
            "- '我是油皮敏感肌，喜欢资生堂'\n"
            "  → {skin_type:['油皮','敏感肌'],brands:['资生堂'],categories:['美妆护肤'],sub_categories:['护肤品']}\n"
            "- '经常出差要便携，不喜欢太重，要支持快充'\n"
            "  → {scenarios:['出差'],avoid_tags:['太重'],must_tags:['快充']}"
        )
        prompt = f"用户输入: {raw_text}\n\nJSON:"

        try:
            from app.model_gateway.gateway import get_model_gateway
            gateway = get_model_gateway()
            response = await gateway.chat(
                capability="intent_understanding",
                prompt=prompt,
                system=system,
            )
            return self._extract_json(response)
        except Exception as e:
            _log.warning(f"Qwen profile parse failed: {e}")
            return None

    @staticmethod
    def _extract_json(response: str) -> dict | None:
        if not response:
            return None
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{[\s\S]*\}", response)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        try:
            cleaned = response.strip()
            cleaned = re.sub(r",\s*}", "}", cleaned)
            cleaned = re.sub(r",\s*]", "]", cleaned)
            return json.loads(cleaned)
        except json.JSONDecodeError:
            _log.debug(f"JSON extraction failed for: {response[:200]}")
            return None


_svc: UserProfileService | None = None


def get_user_profile_service() -> UserProfileService:
    global _svc
    if _svc is None:
        _svc = UserProfileService()
    return _svc
