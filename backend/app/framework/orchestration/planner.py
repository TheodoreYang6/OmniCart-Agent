"""Planner —— 按 intent / query 复杂度生成 ExecutionPlan。

三层结构（Phase 6-B2）：
- ``RulePlanner``：意图模板，0 延迟，覆盖 90%+ 单意图流量；
- ``LLMPlanner``：复杂/多步 query 由 LLM 在封闭能力词表内编排计划，
  PlanValidator 硬校验 + 双层缓存（进程内 + Redis）；
- ``HybridPlanner``：规则复杂度探测触发，任何失败降级规则（LLM -> 规则 -> 不崩）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from abc import ABC, abstractmethod

from app.framework.orchestration.plan import ExecutionPlan, PlanStep

logger = logging.getLogger(__name__)

__all__ = [
    "Planner",
    "RulePlanner",
    "LLMPlanner",
    "HybridPlanner",
    "get_planner",
    "extract_compare_targets",
    "set_tool_schema_source",
]


# LLM 可见工具 schema 的来源钩子（P0-2 依赖治理）：framework 不得 import providers，
# 由 providers/tools 装配时注入（providers → framework 合法方向）。未注入时返回空
# 列表，LLMPlanner 退化为纯 capability 词表规划（fail-open）。
_tool_schema_source = None


def set_tool_schema_source(fn) -> None:
    """注入 "返回 LLM 可见工具 openai schema 列表" 的回调（装配时调一次）。"""
    global _tool_schema_source
    _tool_schema_source = fn


# 对比意图触发词（尾部剥离）与实体分隔符
_COMPARE_TAIL = re.compile(
    r"(做对比|做比较|对比|比较|哪个更好|哪个好|哪款好|怎么选|如何选|选哪个|哪个强)+[的呢吗?？!！~～\s]*$"
)
_COMPARE_SEP = re.compile(r"\s*(?:和|与|跟|还是|、|[Vv][Ss]\.?)\s*")


def extract_compare_targets(query: str) -> list[str]:
    """从对比 query 中提取对比实体（规则版；提不出返回 []，调用方回退单路检索）。

    "索尼和Bose的耳机对比哪个好" -> ["索尼", "Bose的耳机"]
    "对airpods和huawei freebuds pro5做对比" -> ["airpods", "huawei freebuds pro5"]
    "对比airpods和huawei freebuds pro5" -> ["airpods", "huawei freebuds pro5"]
    """
    # FollowUpEngine 可能在原句后拼 "\n\n上下文提示"，只取首行避免污染实体
    q = (query or "").strip().split("\n")[0].strip()
    for noise in ("帮我", "请", "麻烦"):
        q = q.replace(noise, "")
    # 先剥句首对比引导词（"对比X和Y"），再剥句首介词"对"（"对X和Y做对比"）；顺序不可反
    q = re.sub(r"^(对比一下|比较一下|对比|比较)", "", q)
    if q.startswith("对"):
        q = q[1:]
    q = _COMPARE_TAIL.sub("", q).strip()
    # ``str.strip`` intentionally receives a character set: comparison edges
    # may contain any mixture of Chinese/ASCII punctuation and the particle “的”.
    parts = [p.strip(" ，,。的 ") for p in _COMPARE_SEP.split(q)]  # noqa: B005
    parts = [p for p in parts if p and len(p) >= 2]
    return parts[:3] if len(parts) >= 2 else []


class Planner(ABC):
    """规划器抽象 —— LLM 版实现同一接口即可热替换。"""

    @abstractmethod
    async def plan(self, state) -> ExecutionPlan: ...


class RulePlanner(Planner):
    """规则模板规划器：intent → 差异化步骤序列。

    - chitchat: 直达 response
    - risk_check: 跳过 reranker（风险问答重证据不重排序，省一次 LLM 精排）
    - compare: reranker 与 evidence_check 并行（二者均只依赖 retrieval）
    - 其余（recommend/alternative/compatibility_check/默认）: 完整链路（与 legacy 等价）
    有图片时统一前置 visual。
    """

    async def plan(self, state) -> ExecutionPlan:
        intent = state.intent or "recommend"
        has_image = bool(state.image_url)

        if intent == "chitchat" and not has_image:
            return self._build(intent, [("response", None)], rationale="闲聊直达回复")

        if intent == "risk_check":
            steps = [("retrieval", None), ("evidence_check", None), ("decision", None), ("response", None)]
            return self._build(intent, steps, has_image, rationale="风险核查跳过精排")

        if intent == "compare":
            # 对比目标分解：提得出实体 -> 多目标并行检索（compare_retrieval），
            # 避免单次混合检索稀释品牌信号造成假阴性；提不出则回退单路。
            targets = extract_compare_targets(state.user_query)
            if targets:
                steps = [
                    ("compare_retrieval", None),
                    ("reranker", "g1"),
                    ("evidence_check", "g1"),
                    ("decision", None),
                    ("response", None),
                ]
                plan = self._build(intent, steps, has_image, rationale=f"对比目标分解: {targets}，多路并行检索")
                plan.meta["compare_targets"] = targets
                return plan
            steps = [
                ("retrieval", None),
                ("reranker", "g1"),
                ("evidence_check", "g1"),
                ("decision", None),
                ("response", None),
            ]
            return self._build(intent, steps, has_image, rationale="对比意图并行精排与证据检查")

        # QU V2 新意图模板
        if intent == "bundle":
            # 多目标拆分检索（sub_queries 由 Router QU 写入；缺失时 capability 内部退化单路）
            steps = [
                ("multi_query_retrieval", None),
                ("reranker", None),
                ("evidence_check", None),
                ("decision", None),
                ("response", None),
            ]
            n = len(state.retrieval_plan.sub_queries or [])
            return self._build(intent, steps, has_image, rationale=f"搭配成套：{n} 路并行分组检索")

        if intent == "replenish":
            # 复购：先查订单历史（B2 工具步回填 context）再检索同款/同类
            steps = [
                ("tool:order.list", None),
                ("retrieval", None),
                ("reranker", None),
                ("evidence_check", None),
                ("decision", None),
                ("response", None),
            ]
            return self._build(intent, steps, has_image, rationale="复购：先查订单再检索")

        if intent == "knowledge":
            # 购物知识：轻检索重解释，不跑重排/决策（不硬塞商品卡）
            steps = [("retrieval", None), ("response", None)]
            plan = self._build(intent, steps, has_image, rationale="知识科普：轻检索重解释")
            plan.meta["knowledge"] = True
            return plan

        # gift 与 recommend 同管线（差异在 response prompt 的 gift_profile 注入）
        steps = [
            ("retrieval", None),
            ("reranker", None),
            ("evidence_check", None),
            ("decision", None),
            ("response", None),
        ]
        return self._build(intent, steps, has_image, rationale="默认完整链路")

    @staticmethod
    def _build(intent: str, caps: list[tuple], has_image: bool = False, rationale: str = "") -> ExecutionPlan:
        """把 (capability, parallel_group) 序列组装为线性依赖计划。

        依赖规则：每步依赖「上一批」全部步骤（同 parallel_group 视为一批）。
        """
        if has_image:
            caps = [("visual", None), *caps]
        steps: list[PlanStep] = []
        prev_batch: list[str] = []
        cur_group: str | None = None
        cur_batch: list[str] = []
        for i, (cap, group) in enumerate(caps, 1):
            sid = f"s{i}_{cap.replace('tool:', 'tool_')}"
            if group is None or group != cur_group:
                if cur_batch:
                    prev_batch = cur_batch
                cur_batch = []
                cur_group = group
            steps.append(PlanStep(step_id=sid, capability=cap, depends_on=list(prev_batch), parallel_group=group))
            cur_batch.append(sid)
        from app.core.config import REFLECT_MAX_RETRIES

        return ExecutionPlan(intent=intent, steps=steps, max_reflects=REFLECT_MAX_RETRIES, rationale=rationale)


_planner: Planner | None = None


# ================================================================
# 复杂度探测（规则版，宁漏勿滥：单意图永远走规则模板）
# ================================================================

_CONJUNCTION = re.compile(r"然后|接着|顺便|之后|再(?:帮|给|推荐|看|查)|先.{1,12}?(?:再|后)")
_CONDITIONAL = re.compile(r"如果.{1,16}?就|要是.{1,16}?就|有货的话")
_ACTION_WORDS = ("订单", "购物车", "物流", "库存", "买过", "买的")
_ADVISE_WORDS = ("推荐", "类似", "好用", "适合", "哪款", "推个")


def _is_complex(query: str) -> tuple[bool, str]:
    """多步/跨域 query 探测，返回 (是否复杂, 触发原因)。"""
    q = (query or "").strip().split("\n")[0]
    if _CONDITIONAL.search(q):
        return True, "conditional"
    if _CONJUNCTION.search(q):
        return True, "multi_step"
    if any(w in q for w in _ACTION_WORDS) and any(w in q for w in _ADVISE_WORDS):
        return True, "cross_domain"
    return False, ""


def _strip_json_fence(raw: str) -> dict:
    """宽容 JSON 提取（与 RouterAgent._parse_llm 同源逻辑）。"""
    raw = (raw or "").strip()
    if "```" in raw:
        block = raw.split("```")[1]
        if block.startswith("json"):
            block = block[4:]
        raw = block.strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, IndexError):
        return {}


# pipeline 能力描述（工具描述取自 ToolSpec，单一事实源；此处只描述图节点）
_PIPELINE_DESC = (
    "- retrieval: 按用户需求检索候选商品与证据\n"
    "- compare_retrieval: 对比意图多目标并行检索（query 含两个对比实体时用）\n"
    "- reranker: 对检索结果语义精排\n"
    "- evidence_check: 检查证据充足性\n"
    "- decision: 候选商品评分与决策分析\n"
    "- response: 生成最终回答（每个计划必须以它结尾）\n"
    "- visual: 解析用户上传的商品图片（仅有图时用）"
)


class LLMPlanner(Planner):
    """LLM 编排计划：封闭词表 + 硬校验 + 双层缓存；失败返 None 由上层降级。"""

    _CACHE_MAX = 128

    def __init__(self):
        self._cache: dict[str, dict] = {}  # 进程内：key -> 已校验计划 model_dump

    async def plan(self, state) -> ExecutionPlan:  # pragma: no cover — 统一走 plan_or_none
        plan = await self.plan_or_none(state, "direct")
        if plan is None:
            raise RuntimeError("llm_plan_failed")
        return plan

    async def plan_or_none(self, state, trigger: str) -> ExecutionPlan | None:
        try:
            key = hashlib.md5(f"{state.user_query}|{state.intent}|{bool(state.image_url)}".encode()).hexdigest()
            if key in self._cache:
                return ExecutionPlan(**self._cache[key])

            from app.core.cache import cached, make_key
            from app.core.config import REDIS_CACHE_TTL_REWRITE

            async def _do_plan() -> dict:
                raw = await self._call_llm(state)
                validated = self._validate(raw, state.intent or "recommend", trigger)
                return validated.model_dump() if validated else {}

            dumped = await cached(make_key("llm_plan", key), REDIS_CACHE_TTL_REWRITE, _do_plan)
            if not dumped or not dumped.get("steps"):
                return None
            if len(self._cache) >= self._CACHE_MAX:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = dumped
            return ExecutionPlan(**dumped)
        except Exception as e:  # noqa: BLE001 — 任何异常降级规则
            logger.warning(f"LLM planner failed, falling back to rules: {e}")
            return None

    async def _call_llm(self, state) -> dict:
        from app.model_gateway.gateway import get_model_gateway
        from app.prompts.agent_prompts import build_planning_prompt

        tools_desc = "\n".join(
            f"- tool:{s['function']['name']}: {s['function']['description']}" for s in self._llm_tool_schemas()
        )
        prompt = build_planning_prompt(state.user_query, _PIPELINE_DESC, tools_desc)
        raw = await get_model_gateway().chat("planning", prompt)
        return _strip_json_fence(raw)

    def _validate(self, raw: dict, intent: str, trigger: str) -> ExecutionPlan | None:
        from app.framework.orchestration.validator import PlanValidator

        allowed = {s["function"]["name"] for s in self._llm_tool_schemas()}
        return PlanValidator(allowed).validate(raw, intent, trigger)

    @staticmethod
    def _llm_tool_schemas() -> list[dict]:
        if _tool_schema_source is None:
            return []
        return _tool_schema_source()


class HybridPlanner(Planner):
    """分层规划：复杂 query 且 flag 开 -> LLM；其余/失败 -> 规则模板。"""

    def __init__(self):
        self._rule = RulePlanner()
        self._llm = LLMPlanner()

    async def plan(self, state) -> ExecutionPlan:
        from app.core.config import ENABLE_LLM_PLANNER  # 调用时读，测试可 monkeypatch

        if ENABLE_LLM_PLANNER:
            complex_, reason = _is_complex(state.user_query)
            if complex_:
                plan = await self._llm.plan_or_none(state, reason)
                if plan is not None:
                    return plan
        return await self._rule.plan(state)


def get_planner() -> Planner:
    """进程级单例：HybridPlanner（flag 关时行为与纯规则完全一致）。"""
    global _planner
    if _planner is None:
        _planner = HybridPlanner()
    return _planner
