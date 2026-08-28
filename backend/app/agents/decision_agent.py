"""V1 Decision Agent — 约束求解 + LLM 证据评估 + 规则评分 + 风险识别。

流程:
1. 从 retrieved_products 的 dict 直接重建 Product 对象
2. 硬约束过滤（预算、品类、必备标签）
3. LLM 证据评估（批量读取 rag_knowledge → 逐件评分+理由）
4. 规则评分（budget_fit, value_score, spec_quality 兜底）
5. 混合排序输出
"""

import asyncio
import logging
from app.agents.base import BaseAgent
from app.core.config import FAST_MODE, ENABLE_DECISION_LLM, DECISION_LLM_TIMEOUT, ENABLE_EVIDENCE_SCORING, SCORE_VERSION
from app.decision.scoring import DecisionScoring
from app.decision.evidence_metrics import EvidenceScoringHelper
from app.retrieval.llm_evaluator import LlmEvaluator
from app.services.category_normalization import normalize_category
from app.services.recommendation_score import build_recommendation_score
from app.schemas.a2a import AgentCard
from app.schemas.product import Product
from app.schemas.workflow import WorkflowState

_log = logging.getLogger(__name__)


class DecisionAgent(BaseAgent):

    def __init__(self, repo=None):
        super().__init__()
        self._scorer = DecisionScoring()
        self._llm_evaluator = LlmEvaluator()

    def _build_card(self) -> AgentCard:
        return AgentCard(
            agent_id="decision",
            name="Decision Agent",
            description="约束求解 + LLM证据评估 + 规则评分 + 风险识别 + 证据绑定",
            capabilities=["constraint_solving", "llm_evaluation", "scoring", "risk_analysis", "evidence_binding"],
            input_schema={"retrieved_products": "list[dict]", "evidence_list": "list[dict]"},
            output_schema={"decision_results": "list[dict]"},
        )

    async def execute(self, state: WorkflowState) -> WorkflowState:
        action = "evidence_scoring"
        n_candidates = len(state.retrieved_products)
        self._start_trace(state, action, f"candidates={n_candidates}, llm_enabled={ENABLE_DECISION_LLM}")

        try:
            # V9 的候选已经通过闭集 Filter 收敛。不能再把它们送进旧的
            # ``final_score`` 混合器，否则 RAG 相似度会反向覆盖 Filter 结论，
            # 并在 UI 上产生“低分却强推荐”的矛盾。
            # 单品聚焦是可信 ``product_id`` 锁定的受控范围。它不需要再经由
            # 泛检索生成 v9 report，但展示结论也必须使用 v9 的确定性评分；
            # 否则会回退到旧 final_score，造成“问欧米”没有指数、标签与普通
            # 推荐不一致的问题。
            if ((state.structured_retrieval_report or {}).get("version") == "v9" or
                    state.retrieval_scope == "exact_product"):
                return self._execute_v9(state)

            constraints = state.constraints
            constraints_dict = {
                "category": constraints.category, "sub_category": constraints.sub_category,
                "budget_max": constraints.budget_max, "budget_min": constraints.budget_min,
                "scenario": constraints.scenario,
            }

            # ---- V4: Evidence-Grounded Scoring ----

            # 1. Build evidence profiles
            helper = EvidenceScoringHelper()
            profiles = helper.build_profiles(state.evidence_list, state.retrieved_products)

            # 2. Optional LLM Evaluator (disabled by default)
            llm_eval_result = {"evaluations": [], "overall_analysis": "", "user_warnings": []}
            if ENABLE_DECISION_LLM and state.retrieved_products:
                try:
                    llm_eval_result = await asyncio.wait_for(
                        self._llm_evaluator.evaluate(
                            query=state.user_query,
                            constraints=constraints_dict,
                            candidates=state.retrieved_products,
                            top_n=5,
                        ),
                        timeout=DECISION_LLM_TIMEOUT,
                    )
                    state.trace_steps.append({
                        "step_id": f"T{len(state.trace_steps) + 1:03d}",
                        "agent_name": "LLM Evaluator (optional)",
                        "action": "evidence_evaluation",
                        "input_summary": f"{n_candidates} candidates",
                        "output_summary": f"evaluated={len(llm_eval_result.get('evaluations',[]))}",
                        "latency_ms": 0, "status": "success",
                    })
                except Exception as e:
                    _log.debug(f"LLM evaluator skipped/timeout: {e}")

            eval_map: dict[str, dict] = {}
            for ev in llm_eval_result.get("evaluations", []):
                eval_map[ev.get("product_id", "")] = ev
            state.llm_overall_analysis = llm_eval_result.get("overall_analysis", "")
            state.llm_user_warnings = llm_eval_result.get("user_warnings", [])

            # 3. Global evidence sufficiency from Evidence Check node
            global_ev_sufficient = state.sufficiency_report.get("sufficient", True) if state.sufficiency_report else True

            # 4. Score each product with RAG evidence
            results = []
            for item in state.retrieved_products:
                pid = item.get("product_id", "")
                try:
                    product = Product(
                        product_id=pid,
                        title=item.get("title", ""), brand=item.get("brand", ""),
                        category=item.get("category", ""), sub_category=item.get("sub_category", ""),
                        base_price=float(item.get("price", 0)),
                        image_path=(item.get("image_urls") or [""])[0],
                        skus=item.get("skus") or [],
                        rag_knowledge=item.get("rag_knowledge") or {},
                    )
                except Exception:
                    continue

                # 硬约束过滤
                hc_failed = not self._passes_hard_constraints(product, constraints)

                # Evidence profile for this product
                profile = profiles.get(pid)
                rag_rel, rel_src = 0.0, "no_evidence"
                ev_metrics = None
                support_ids = []

                if ENABLE_EVIDENCE_SCORING and profile:
                    rag_rel, rel_src = helper.compute_rag_relevance(item, profile, state.user_query)
                    ev_metrics = helper.compute_metrics(
                        pid, profile, state.user_query, constraints_dict, state.intent
                    )
                    support_ids = ev_metrics.support_evidence_ids

                llm_ev = eval_map.get(pid, {})
                # 偏好只从结构化 MemoryBank 投影读取。曾经从 ``context_prompt``
                # 反解析“偏好品牌:”不仅脆弱，还会让 FollowUp/工具文本变成评分的
                # 第二真相；会话最终上下文也因此可能与排序依据不一致。
                preferred_brands = self._preferred_brands(state.used_memories)

                decision = self._scorer.score_with_evidence(
                    product=product,
                    query=state.user_query,
                    keyword_score=item.get("score", 0.0),
                    budget_max=constraints.budget_max,
                    scenario=constraints.scenario,
                    visual_result=state.visual_result,
                    used_memories=state.used_memories,
                    preferred_brands=preferred_brands,
                    llm_relevance=llm_ev.get("relevance", 0.0),
                    llm_reasoning=llm_ev.get("reasoning", ""),
                    llm_verdict=llm_ev.get("verdict", ""),
                    llm_strengths=llm_ev.get("strengths", []),
                    llm_risks=llm_ev.get("risks", []),
                    force_rag_relevance=rag_rel,
                    relevance_source=rel_src,
                    evidence_metrics=ev_metrics,
                    support_evidence_ids=support_ids,
                    global_evidence_sufficient=global_ev_sufficient,
                    scenario_keywords=constraints.scenario_keywords if hasattr(constraints, 'scenario_keywords') else None,
                    spec_keywords=constraints.spec_keywords if hasattr(constraints, 'spec_keywords') else None,
                )

                # 避雷商品应在检索层已被硬过滤，此处仅记录漏网之鱼
                exclude_hit = any(
                    tag.lower() in product.title.lower() or tag.lower() in product.brand.lower()
                    for tag in (constraints.exclude_tags or [])
                )
                if exclude_hit:
                    _log.warning(f"Exclude tag leak: {product.product_id} matched {constraints.exclude_tags}")

                # Override for hard constraint failures (品类/预算不匹配)
                # 拍照识图时品类来自视觉识别，可能与DB分类不一致，不降分
                if hc_failed and not state.visual_result:
                    decision.final_score = min(decision.final_score, 0.45)
                    decision.display_score = round(decision.final_score * 10, 1)
                    decision.recommendation_level = "not_recommended"
                    decision.hard_constraint_status = "failed"

                results.append(decision.model_dump())

                # Debug log
                _log.debug(
                    f"Decision: {pid} rag_rel={rag_rel:.3f}({rel_src}) "
                    f"ev_conf={ev_metrics.evidence_confidence if ev_metrics else 0:.3f} "
                    f"final={decision.final_score:.3f} level={decision.recommendation_level}"
                )

            # ``final_score`` 仅保留作旧接口兼容/内部排序，用户决策以闭集 Filter
            # verdict + 硬约束 + 证据状态为准，不能再被 0~10 展示分反向覆盖。
            result_by_id = {r.get("product_id"): r for r in results}
            v9 = (state.structured_retrieval_report or {}).get("version") == "v9"
            bucket_level = {
                "primary": "strong_recommend", "alternative": "recommended",
                "conditional": "worth_considering", "exclude": "not_recommended",
            }
            for index, item in enumerate(state.retrieved_products or []):
                result = result_by_id.get(item.get("product_id"))
                if not result:
                    continue
                verdict = str(item.get("filter_bucket") or "")
                result["retrieval_rank"] = index + 1
                result["filter_verdict"] = verdict or "legacy"
                # Deprecated contract field: clients must use match/evidence labels.
                result["display_score"] = 0.0
                if result.get("hard_constraint_status") == "failed":
                    result["recommendation_level"] = "not_recommended"
                elif v9 and verdict:
                    result["recommendation_level"] = bucket_level.get(verdict, "worth_considering")
                elif result.get("recommendation_level") not in {"insufficient_evidence", "cautious"}:
                    result["recommendation_level"] = self._level_of(float(result.get("final_score") or 0))
            # Preserve V9 Filter order.  Legacy pipeline still receives a stable
            # score ordering, but no numeric score is exposed as UX semantics.
            if not v9:
                results.sort(key=lambda r: r["final_score"], reverse=True)
            state.decision_results = results
            state.scoring_trace = {
                "version": "verdict_evidence_v1",
                "v9_filter_active": v9,
                "signals": ["filter_verdict", "hard_constraints", "evidence_confidence", "retrieval_rank"],
                "deprecated_display_score": True,
            }

            risky = sum(1 for r in results if r.get("recommendation_level") in {"cautious", "not_recommended"})
            high = sum(1 for r in results if r.get("recommendation_level") in {"strong_recommend", "recommended"})
            ev_tag = " [EVIDENCE_INSUFFICIENT]" if not global_ev_sufficient else ""
            summary = f"evidence scored={len(results)}, favorable={high}, cautious={risky}{ev_tag}"
            return self._finish_trace(state, summary)

        except Exception as e:
            return self._error_trace(state, str(e))

    def _execute_v9(self, state: WorkflowState) -> WorkflowState:
        """V9 展示裁决：只用可复算的本轮信号，不调用旧评分体系。"""
        results: list[dict] = []
        expected_category = normalize_category(state.constraints.category)
        budget_max = state.constraints.budget_max
        for index, raw_product in enumerate(state.retrieved_products or []):
            product = dict(raw_product)
            if (state.retrieval_scope == "exact_product" and
                    product.get("product_id") in set(state.resolved_product_ids or [state.focus_product_id])):
                # 用户已明确锁定这件商品时，指数描述的是“是否满足当前追问”，
                # 不能因为没有走泛推荐 Filter 而被默认判成 conditional。
                product.setdefault("filter_bucket", "primary")
            price = product.get("price")
            hard_failed = False
            try:
                hard_failed = bool(budget_max is not None and float(price or 0) > float(budget_max))
            except (TypeError, ValueError):
                pass
            if expected_category and product.get("category") != expected_category:
                hard_failed = True
            product["hard_constraint_status"] = "failed" if hard_failed else "pass"
            score = build_recommendation_score(product, state.constraints)
            risks: list[str] = []
            if hard_failed:
                risks.append("未满足本次预算或品类条件")
            elif score["evidence_label"] == "信息有限":
                risks.append("部分商品资料有限，购买前建议再确认")
            reason = str(product.get("card_reason") or "").strip()
            if not reason:
                reason = score["dimensions"][0]["detail"]
            result = {
                "product_id": product.get("product_id", ""),
                "recommendation_score": score,
                "recommendation_level": score["recommendation_level"],
                "match_label": score["match_label"],
                "evidence_label": score["evidence_label"],
                "why_it_fits": reason,
                "recommendation_reason": reason,
                "caution": "；".join(risks),
                "risk_factors": risks,
                "hard_constraint_status": product["hard_constraint_status"],
                "filter_verdict": str(product.get("filter_bucket") or "conditional"),
                "retrieval_rank": index + 1,
            }
            results.append(result)
        state.decision_results = results
        state.scoring_trace = {
            "version": "omi_recommendation_v1",
            "user_visible_signals": ["filter_verdict", "need_fit", "budget_fit", "information"],
            "internal_only_signals": ["chunk_aggregate_score", "rerank_relevance"],
        }
        favorable = sum(1 for item in results if item["recommendation_level"] in {"strong_recommend", "recommended"})
        return self._finish_trace(state, f"v9 deterministic display scores={len(results)}, favorable={favorable}")

    # 品牌品类映射: "日系"等品类词 → 具体品牌列表
    _BRAND_CATEGORY_MAP = {
        "日系": ["资生堂", "SK-II", "SK2", "雪肌精", "黛珂", "CPB", "肌肤之钥",
                 "植村秀", "城野医生", "珂润", "Fancl", "芳珂", "DHC", "奥尔滨",
                 "茵芙莎", "IPSA", "苏菲娜", "Sofina", "嘉娜宝", "Kanebo"],
        "韩系": ["兰芝", "悦诗风吟", "雪花秀", "Whoo", "后", "赫拉", "HERA",
                 "IOPE", "梦妆", "Mamonde", "蒂佳婷", "Dr.Jart"],
        "欧美": ["雅诗兰黛", "兰蔻", "欧莱雅", "科颜氏", "娇韵诗", "倩碧",
                 "雅顿", "赫莲娜", "理肤泉", "薇姿", "修丽可", "海蓝之谜", "La Mer"],
    }

    @classmethod
    def _level_of(cls, score: float) -> str:
        """按真实 final_score 生成推荐等级，避免展示分校准影响用户判断。"""
        if score >= 0.80:
            return "strong_recommend"
        if score >= 0.65:
            return "recommended"
        if score >= 0.50:
            return "worth_considering"
        return "cautious"

    def _passes_hard_constraints(self, product, constraints) -> bool:
        """硬约束判断 — 不满足则直接过滤。

        must_tags 改为软约束: 不匹配不会直接过滤，改为在评分中扣分。
        只有品类完全错误或排除标签命中才硬过滤。
        """
        # 预算硬上限 (超过2倍预算直接过滤)
        if constraints.budget_max and product.base_price > constraints.budget_max * 2:
            return False

        # 品类值可能来自模型或旧客户端；仅对受控词表中的值施加硬限制。
        expected_category = normalize_category(constraints.category)
        if expected_category and product.category != expected_category:
            return False

        # 排除标签: 改为软降权（在评分阶段扣分），不再硬过滤
        # 原因: Router LLM 可能从"也可以不是苹果"误提取 avoid=['苹果']
        #       硬过滤会导致整个品牌消失，软降权更安全
        return True

    @staticmethod
    def _preferred_brands(used_memories: list[dict]) -> list[str]:
        """从可追溯的长期偏好投影提取品牌，拒绝解析自由文本提示词。"""
        brands: list[str] = []
        seen: set[str] = set()
        for memory in used_memories or []:
            if not isinstance(memory, dict) or memory.get("memory_type") != "brand":
                continue
            value = memory.get("structured_value") or {}
            brand = str(value.get("brand") or "").strip() if isinstance(value, dict) else ""
            key = brand.casefold()
            if brand and key not in seen:
                seen.add(key)
                brands.append(brand)
        return brands
