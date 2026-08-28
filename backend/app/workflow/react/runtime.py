"""受控工具运行时。

借鉴 pi 的 agent loop，把“是否可调、如何执行、怎样把结果写回状态、何时停止”
从 ReAct 节点和具体工具中抽离。工具仍通过 ToolRegistry 执行；本模块只负责
请求级策略与确定性的状态归并，不向客户端暴露内部推理或工具参数。
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.framework.tools.protocols import ToolResult
from app.schemas.workflow import WorkflowState
from app.workflow.react.common import build_tool_ctx, summarize_result, trace

__all__ = ["ToolPolicy", "ToolRuntime", "runtime_context_summary"]


_ALTERNATIVE_WORDS = ("对比", "替代", "同类", "更好选择", "其他选择")


@dataclass(slots=True)
class _PreparedCall:
    call: dict[str, Any]
    tool: Any | None
    signature: str
    group_id: str
    blocked_reason: str = ""


def _normalise_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value)


def _ngram_similarity(left: str, right: str) -> float:
    """保守的中文近似重复判断；只用于阻止同一目标的无价值重搜。"""
    left, right = _normalise_text(left), _normalise_text(right)
    if not left or not right:
        return 0.0
    if left == right or left in right or right in left:
        return 1.0
    if min(len(left), len(right)) < 4:
        return 0.0
    a = {left[i:i + 2] for i in range(len(left) - 1)}
    b = {right[i:i + 2] for i in range(len(right) - 1)}
    return len(a & b) / max(1, len(a | b))


def _allowed_ids(state: WorkflowState) -> set[str]:
    return {
        *[str(pid) for pid in (state.resolved_product_ids or []) if pid],
        *[str(p.get("product_id")) for p in (state.retrieved_products or []) if p.get("product_id")],
    }


class ToolPolicy:
    """对应 pi 的 beforeToolCall：预算、范围和重复调用都在这里裁决。"""

    @staticmethod
    def budget_for(state: WorkflowState) -> dict[str, int]:
        if state.mode == "max" or state.tool_runtime_mode == "deep":
            return {"llm_turns": 4, "shopping.search": 3, "shopping.compare": 1}
        return {"llm_turns": 0, "shopping.search": 1, "shopping.compare": 1}

    @classmethod
    def initialise(cls, state: WorkflowState, *, mode: str) -> None:
        state.tool_runtime_mode = mode
        if not state.tool_budget:
            limits = cls.budget_for(state)
            # 普通模式只有一个 search *批次*；当 Router 合法拆出多个独立目标时，
            # 该批次内允许每组各一次，避免预算面板出现 3/1 这种误导性计数。
            if mode == "normal" and len(state.retrieval_plan.sub_queries or []) > 1:
                limits["shopping.search"] = len(state.retrieval_plan.sub_queries)
            state.tool_budget = {"limits": limits, "used": {}}

    @staticmethod
    def _group_id(state: WorkflowState, call: dict[str, Any]) -> str:
        args = call.get("args") or {}
        explicit = str(args.get("_group_id") or "").strip()
        if explicit:
            return explicit
        query = _normalise_text(str(args.get("query") or ""))
        for index, sub in enumerate(state.retrieval_plan.sub_queries or [], 1):
            if _normalise_text(sub.query) == query:
                return f"plan:{index}"
        return "main"

    @staticmethod
    def _next_uncovered_group(state: WorkflowState, reserved_groups: set[str] | None = None) -> tuple[int, Any] | None:
        """返回 Router 明确拆分但尚未成功检索的下一个目标。"""
        completed = {
            str(item.get("group_id") or "")
            for item in state.tool_ledger
            if item.get("name") == "shopping.search" and item.get("status") == "success"
        }
        completed.update(reserved_groups or set())
        for index, sub in enumerate(state.retrieval_plan.sub_queries or [], 1):
            if f"plan:{index}" not in completed:
                return index, sub
        return None

    @classmethod
    def _bind_search_to_router_group(
        cls, state: WorkflowState, call: dict[str, Any], reserved_groups: set[str] | None = None,
    ) -> dict[str, Any]:
        """把深度 Loop 的泛化 search 绑定到尚未覆盖的 Router 子目标。

        ReAct 模型常把“零食和饮品”改写成一个泛词，旧实现会让两次搜索都落到
        ``main``，后一次甚至覆盖另一类目的交付。Router 已经给出独立目标时，
        服务端必须以它作为搜索范围的真源；模型仍负责决定是否需要下一次搜索，
        但不能重新发明或混合分组。
        """
        if not state.retrieval_plan.sub_queries:
            return call
        args = dict(call.get("args") or {})
        matched = cls._group_id(state, {**call, "args": args})
        if matched != "main":
            return {**call, "args": args}
        next_group = cls._next_uncovered_group(state, reserved_groups)
        if next_group is None:
            return {**call, "args": args}
        index, sub = next_group
        args["_group_id"] = f"plan:{index}"
        args["query"] = sub.query
        if sub.category:
            args["category"] = sub.category
        if sub.budget_hint is not None:
            args["budget_max"] = sub.budget_hint
        return {**call, "args": args}

    @classmethod
    def _signature(cls, state: WorkflowState, call: dict[str, Any], group_id: str) -> str:
        args = call.get("args") or {}
        stable = {
            "name": str(call.get("name") or ""),
            "group": group_id,
            "query": _normalise_text(str(args.get("query") or "")),
            "category": _normalise_text(str(args.get("category") or state.constraints.category or "")),
            "budget": args.get("budget_max", state.constraints.budget_max),
            "focus": str(args.get("focus") or ""),
            "scope": state.retrieval_scope,
            "allowed": sorted(_allowed_ids(state)),
            "must": list(state.retrieval_plan.must_constraints or state.constraints.must_tags or []),
            "avoid": list(state.retrieval_plan.avoid_constraints or state.constraints.exclude_tags or []),
        }
        raw = repr(stable).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:24]

    @classmethod
    def _used(cls, state: WorkflowState, name: str) -> int:
        return sum(1 for item in state.tool_ledger if item.get("name") == name and item.get("status") != "blocked")

    @classmethod
    def _seen_search(cls, state: WorkflowState, query: str, group_id: str) -> bool:
        for item in state.tool_ledger:
            if item.get("name") != "shopping.search" or item.get("status") == "blocked":
                continue
            if item.get("group_id") == group_id and _ngram_similarity(query, str(item.get("query") or "")) >= 0.86:
                return True
        return False

    @classmethod
    def prepare(cls, state: WorkflowState, call: dict[str, Any], registry) -> _PreparedCall:
        name = str(call.get("name") or "")
        args = dict(call.get("args") or {})
        call = {**call, "name": name, "args": args}
        if name == "shopping.search" and state.mode == "max":
            call = cls._bind_search_to_router_group(state, call)
            args = dict(call["args"])
        tool = registry.get_optional(name)
        group_id = cls._group_id(state, call)
        signature = cls._signature(state, call, group_id)
        if tool is None:
            return _PreparedCall(call, None, signature, group_id, "未知工具")

        required = (getattr(tool.spec, "parameters", None) or {}).get("required") or []
        missing = [key for key in required if args.get(key) in (None, "", [])]
        if missing:
            return _PreparedCall(call, tool, signature, group_id, "缺少必要参数：" + "、".join(missing))
        properties = (getattr(tool.spec, "parameters", None) or {}).get("properties") or {}
        expected_types = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "array": list,
            "object": dict,
            "boolean": bool,
        }
        for key, value in args.items():
            if key.startswith("_") or value is None or key not in properties:
                continue
            schema_type = properties[key].get("type")
            expected = expected_types.get(schema_type)
            # bool 是 int 的子类，但不能作为价格/数量接受。
            valid = isinstance(value, expected) and not (schema_type in {"number", "integer"} and isinstance(value, bool))
            if expected is not None and not valid:
                return _PreparedCall(call, tool, signature, group_id, f"参数 {key} 类型无效")

        limits = (state.tool_budget or {}).get("limits") or cls.budget_for(state)
        if name in limits and cls._used(state, name) >= int(limits[name]):
            return _PreparedCall(call, tool, signature, group_id, f"{name} 已达到本次请求的调用上限")

        if name == "shopping.search":
            if state.retrieval_scope in {"exact_product", "product_family"} and not any(
                word in state.user_query for word in _ALTERNATIVE_WORDS
            ):
                return _PreparedCall(call, tool, signature, group_id, "当前已锁定商品或系列，无需泛搜索")
            if cls._seen_search(state, str(args.get("query") or ""), group_id):
                return _PreparedCall(call, tool, signature, group_id, "该检索目标已经完成，无需重复搜索")
            if state.retrieval_plan.sub_queries and group_id == "main" and cls._next_uncovered_group(state) is None:
                return _PreparedCall(call, tool, signature, group_id, "Router 已覆盖全部独立检索目标，无需追加泛搜索")

        if name == "shopping.product_dossier":
            product_id = str(args.get("product_id") or "")
            if any(item.get("name") == name and item.get("product_id") == product_id and item.get("status") == "success"
                   for item in state.tool_ledger):
                return _PreparedCall(call, tool, signature, group_id, "这件商品的完整档案已经建立，无需重复核对")
            if state.focus_product_id and product_id != state.focus_product_id:
                return _PreparedCall(call, tool, signature, group_id, "商品不在当前已锁定范围内")
            if not state.focus_product_id and not (state.retrieval_scope == "exact_product" and len(state.resolved_product_ids) == 1):
                return _PreparedCall(call, tool, signature, group_id, "只有唯一锁定的单品才能建立档案")

        if name == "shopping.compare":
            ids = {str(pid) for pid in (args.get("product_ids") or []) if pid}
            if not ids or not ids <= _allowed_ids(state):
                return _PreparedCall(call, tool, signature, group_id, "对比商品必须来自当前可信锁定范围或已检索候选")

        if signature in state.call_signatures:
            return _PreparedCall(call, tool, signature, group_id, "本轮工具调用与已执行调用重复")
        return _PreparedCall(call, tool, signature, group_id)


class ToolRuntime:
    """对应 pi 的 executeToolCalls + afterToolCall，以隔离状态补丁安全归并工具结果。"""

    @staticmethod
    def _call_id(state: WorkflowState, index: int, call: dict[str, Any]) -> str:
        return str(call.get("id") or f"tool_{state.round_no}_{len(state.tool_ledger) + index + 1}")

    @classmethod
    async def execute_batch(cls, state: WorkflowState, calls: list[dict[str, Any]]) -> WorkflowState:
        from app.providers.tools import get_tool_registry

        ToolPolicy.initialise(state, mode="deep" if state.mode == "max" else "normal")
        registry = get_tool_registry()
        # 以“预占”而不是仅看已落账本的次数执行校验。否则同一个模型回复内的
        # 两个 compare / 同一 dossier 会同时越过上限，破坏工具级预算契约。
        reserved_counts: dict[str, int] = {}
        reserved_signatures: set[str] = set()
        reserved_dossiers: set[str] = set()
        # 同一条模型消息可能并行请求多个搜索。分组绑定不能只看已落账本，
        # 否则它们都会抢到 plan:1，第二个再因重复签名被阻断。
        reserved_search_groups: set[str] = set()
        prepared: list[_PreparedCall] = []
        limits = (state.tool_budget or {}).get("limits") or ToolPolicy.budget_for(state)
        for call in calls:
            if (
                str(call.get("name") or "") == "shopping.search"
                and state.mode == "max"
                and state.retrieval_plan.sub_queries
            ):
                call = ToolPolicy._bind_search_to_router_group(state, call, reserved_search_groups)
            item = ToolPolicy.prepare(state, call, registry)
            if not item.blocked_reason:
                name = item.call["name"]
                if name in limits and ToolPolicy._used(state, name) + reserved_counts.get(name, 0) >= int(limits[name]):
                    item.blocked_reason = f"{name} 已达到本次请求的调用上限"
                elif item.signature in reserved_signatures:
                    item.blocked_reason = "本轮工具调用重复"
                elif name == "shopping.product_dossier" and str(item.call.get("args", {}).get("product_id") or "") in reserved_dossiers:
                    item.blocked_reason = "这件商品的完整档案已经在本轮建立，无需重复核对"
                if not item.blocked_reason:
                    reserved_counts[name] = reserved_counts.get(name, 0) + 1
                    reserved_signatures.add(item.signature)
                    if name == "shopping.product_dossier":
                        reserved_dossiers.add(str(item.call.get("args", {}).get("product_id") or ""))
                    if name == "shopping.search" and item.group_id.startswith("plan:"):
                        reserved_search_groups.add(item.group_id)
            prepared.append(item)
        executable = [item for item in prepared if not item.blocked_reason]

        # 只有 Router 明确分组的独立 search 才允许并行。它们均在隔离快照中运行，
        # 所以工具原有的 state 写入不会相互覆盖；结果仍由下面的 reducer 按调用顺序提交。
        independent_searches = (
            len(executable) > 1
            and all(item.call["name"] == "shopping.search" and item.group_id != "main" for item in executable)
            and len({item.group_id for item in executable}) == len(executable)
        )

        async def invoke(index: int, item: _PreparedCall):
            if item.blocked_reason:
                return index, item, None, ToolResult(ok=False, message=item.blocked_reason), 0
            isolated = item.tool.spec.permission == "read"
            target_state = state.model_copy(deep=True) if isolated else state
            target_state.tool_runtime_group_id = item.group_id
            context = build_tool_ctx(target_state)
            started = time.perf_counter()
            try:
                result = await registry.invoke(item.call["name"], item.call.get("args") or {}, context)
            except Exception as exc:  # noqa: BLE001 - 单工具失败必须回填给模型，不中断整轮
                result = ToolResult(ok=False, error=str(exc))
            elapsed = round((time.perf_counter() - started) * 1000)
            return index, item, target_state if isolated else None, result, elapsed

        tasks = [invoke(index, item) for index, item in enumerate(prepared)]
        outcomes = await asyncio.gather(*tasks) if independent_searches else [await task for task in tasks]
        for index, item, patch_state, result, elapsed in sorted(outcomes, key=lambda row: row[0]):
            cls._reduce(state, item, patch_state, result, elapsed, cls._call_id(state, index, item.call))
        state.pending_tool_calls = []
        cls._apply_stop_policy(state)
        return state

    @staticmethod
    def _merge_products(current: list[dict], incoming: list[dict]) -> list[dict]:
        seen: set[str] = set()
        merged: list[dict] = []
        for row in [*incoming, *current]:
            pid = str(row.get("product_id") or "")
            if pid and pid not in seen:
                seen.add(pid)
                merged.append(row)
        return merged

    @staticmethod
    def _merge_evidence(current: list[dict], incoming: list[dict]) -> list[dict]:
        seen: set[tuple[str, str]] = set()
        merged: list[dict] = []
        for row in [*incoming, *current]:
            key = (str(row.get("product_id") or ""), str(row.get("content") or row.get("text") or "")[:180])
            if key not in seen:
                seen.add(key)
                merged.append(row)
        return merged

    @classmethod
    def _reduce(cls, state: WorkflowState, prepared: _PreparedCall, patch: WorkflowState | None,
                result: ToolResult, elapsed: int, call_id: str) -> None:
        name = prepared.call["name"]
        args = prepared.call.get("args") or {}
        ledger = {
            "tool_call_id": call_id,
            "name": name,
            "group_id": prepared.group_id,
            "query": str(args.get("query") or ""),
            "product_id": str(args.get("product_id") or ""),
            "signature": prepared.signature,
            "round": state.round_no,
            "status": "success" if result.ok else ("blocked" if prepared.blocked_reason else "failed"),
            "latency_ms": elapsed,
            "summary": summarize_result(result)[:240],
        }
        state.tool_ledger.append(ledger)
        used = (state.tool_budget or {}).setdefault("used", {})
        used[name] = int(used.get(name, 0)) + (0 if prepared.blocked_reason else 1)
        state.call_signatures.append(prepared.signature)
        trace(state, name, ledger["summary"][:80], latency_ms=elapsed, status=ledger["status"])
        state.messages.append({"role": "tool", "tool_call_id": call_id, "content": summarize_result(result)})
        for action in (getattr(result, "actions", None) or []):
            if isinstance(action, dict) and action not in state.tool_actions:
                state.tool_actions.append(action)
        if not result.ok or patch is None:
            return

        # 只归并工具实际新增的部分，不接受快照中的旧列表反向覆盖主状态。
        state.retrieved_products = cls._merge_products(state.retrieved_products, patch.retrieved_products)
        state.evidence_list = cls._merge_evidence(state.evidence_list, patch.evidence_list)
        known_groups = {str(item.get("group_id") if isinstance(item, dict) else item.group_id) for item in state.retrieval_groups}
        for group in patch.retrieval_groups:
            gid = str(group.get("group_id") if isinstance(group, dict) else group.group_id)
            if gid and gid not in known_groups:
                state.retrieval_groups.append(group)
                known_groups.add(gid)
        known_candidates = {str(item.get("group_id") or "") for item in state.candidate_groups}
        for group in patch.candidate_groups:
            gid = str(group.get("group_id") or "")
            if gid and gid not in known_candidates:
                state.candidate_groups.append(group)
                known_candidates.add(gid)
        state.candidate_trace.extend(item for item in patch.candidate_trace if item not in state.candidate_trace)
        state.evidence_packs.update(patch.evidence_packs)
        state.llm_filter_result.update(patch.llm_filter_result)
        state.decision_results = cls._merge_products(state.decision_results, patch.decision_results)
        state.product_dossiers.update(patch.product_dossiers)
        state.tool_actions.extend(action for action in patch.tool_actions if action not in state.tool_actions)
        state.skill_executions.extend(item for item in patch.skill_executions if item not in state.skill_executions)
        if patch.structured_retrieval_report:
            state.structured_retrieval_report = patch.structured_retrieval_report
        elif name == "shopping.search" and patch.candidate_groups:
            state.structured_retrieval_report = {"version": "v9", "runtime": "tool"}
        if patch.focus_product_id:
            state.focus_product_id = patch.focus_product_id
            state.retrieval_scope = patch.retrieval_scope
            state.resolved_product_ids = list(patch.resolved_product_ids)
            state.product_resolution = dict(patch.product_resolution)
            state.selected_products = list(patch.selected_products)
            state.selected_reason = patch.selected_reason
        # ``context_prompt`` 是旧检索/追问兼容输入，不是工具结果的归宿。
        # 让隔离工具快照把它反向并回主状态，会重新引入“工具转录混入最终回答”
        # 以及并行任务最后写入者覆盖的问题。最终回答只读 AnswerContext，工具
        # 的完整结构化结果已经在上述候选、证据、档案字段中归并。

    @staticmethod
    def _apply_stop_policy(state: WorkflowState) -> None:
        limits = (state.tool_budget or {}).get("limits") or ToolPolicy.budget_for(state)
        used_search = ToolPolicy._used(state, "shopping.search")
        if used_search >= limits.get("shopping.search", 0):
            state.tool_runtime_stop_reason = "已达到检索预算"
        if any(item.get("name") == "shopping.product_dossier" and item.get("status") == "success"
               for item in state.tool_ledger):
            state.tool_runtime_stop_reason = "单品档案已完成"
        sub_queries = state.retrieval_plan.sub_queries or []
        if used_search and not sub_queries and state.retrieved_products:
            state.tool_runtime_stop_reason = "已获得足够的候选商品"
        if sub_queries and len({item.get("query") for item in state.tool_ledger if item.get("name") == "shopping.search" and item.get("status") == "success"}) >= len(sub_queries):
            state.tool_runtime_stop_reason = "已覆盖全部检索分组"
        if state.tool_runtime_stop_reason:
            state.transition = "finalize"

    @classmethod
    async def run_normal_search(cls, state: WorkflowState) -> WorkflowState:
        """普通模式唯一的受控 search 批次；不启动 LLM 工具循环。"""
        intent = state.intent if state.intent in {"recommend", "compare", "risk_check"} else "recommend"
        sub_queries = state.retrieval_plan.sub_queries or []
        calls: list[dict[str, Any]] = []
        # 多目标仍是一次受控批次，而不是多次普通工作流。只有 Router 明确拆开的
        # 独立目标才拥有各自的 search 调用和结果组；它们能并行执行、稳定归并。
        if len(sub_queries) > 1:
            per_group_top_k = max(3, min(9, (state.retrieval_plan.top_k or 9) // len(sub_queries) + 1))
            for index, sub in enumerate(sub_queries, 1):
                args: dict[str, Any] = {
                    "query": sub.query,
                    "top_k": per_group_top_k,
                    "intent_hint": intent,
                    "_group_id": f"plan:{index}",  # 仅供 ToolPolicy / 账本归组，Registry 会剥离
                }
                if sub.category or state.constraints.category or state.retrieval_plan.category:
                    args["category"] = sub.category or state.constraints.category or state.retrieval_plan.category
                if sub.budget_hint is not None:
                    args["budget_max"] = sub.budget_hint
                elif state.constraints.budget_max is not None:
                    args["budget_max"] = state.constraints.budget_max
                calls.append({"id": f"normal_search_{index}", "name": "shopping.search", "args": args})
        else:
            args = {
                "query": state.user_query,
                "top_k": max(3, min(9, state.retrieval_plan.top_k or 5)),
                "intent_hint": intent,
            }
            if state.constraints.category or state.retrieval_plan.category:
                args["category"] = state.constraints.category or state.retrieval_plan.category
            if state.constraints.budget_max is not None:
                args["budget_max"] = state.constraints.budget_max
            calls.append({"id": "normal_search", "name": "shopping.search", "args": args})
        await cls.execute_batch(state, calls)
        if state.candidate_groups:
            state.structured_retrieval_report = {"version": "v9", "runtime": "normal"}
        return state


def runtime_context_summary(state: WorkflowState) -> str:
    """给下一轮模型的最小可信运行时上下文，避免它看不见已完成工作又重搜。"""
    lines: list[str] = []
    if state.product_resolution or state.resolved_product_ids:
        ids = ", ".join(state.resolved_product_ids[:5]) or "无"
        lines.append(f"[可信商品范围] scope={state.retrieval_scope}; ids={ids}")
    if state.retrieval_plan.sub_queries:
        lines.append("[Router 检索组] " + "；".join(
            f"{index}:{sub.role or sub.query}" for index, sub in enumerate(state.retrieval_plan.sub_queries, 1)
        ))
    limits = (state.tool_budget or {}).get("limits") or ToolPolicy.budget_for(state)
    used = {name: ToolPolicy._used(state, name) for name in ("shopping.search", "shopping.compare")}
    lines.append("[工具预算] " + "；".join(f"{name} {used.get(name, 0)}/{limit}" for name, limit in limits.items() if name != "llm_turns"))
    for item in state.tool_ledger[-4:]:
        lines.append(f"[已执行] {item.get('name')}({item.get('group_id')})：{item.get('status')}；{item.get('summary', '')[:100]}")
    if state.tool_runtime_stop_reason:
        lines.append(f"[收敛要求] {state.tool_runtime_stop_reason}；立即给出最终回答，不再调工具。")
    return "\n".join(lines)
