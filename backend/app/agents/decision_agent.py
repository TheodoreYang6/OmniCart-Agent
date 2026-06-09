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
                # 从 context_prompt 提取偏好品牌传给评分
                preferred_brands = []
                cp = state.context_prompt or ""
                if "偏好品牌:" in cp:
                    brands_part = cp.split("偏好品牌:")[1].split("|")[0].strip()
                    preferred_brands = [b.strip() for b in brands_part.split(",") if b.strip()]

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

                # 排除标签软降权（不硬过滤）
                exclude_hit = any(
                    tag.lower() in product.title.lower() or tag.lower() in product.brand.lower()
                    for tag in (constraints.exclude_tags or [])
                )
                if exclude_hit:
                    decision.final_score = max(0.0, decision.final_score * 0.6)
                    decision.display_score = round(decision.final_score * 10, 1)

                # Override for hard constraint failures (品类/预算不匹配)
                if hc_failed:
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

            # Sort by final_score
            results.sort(key=lambda r: r["final_score"], reverse=True)
            state.decision_results = results

            risky = sum(1 for r in results if r["display_score"] < 5.0)
            high = sum(1 for r in results if r["display_score"] >= 8.0)
            ev_tag = " [EVIDENCE_INSUFFICIENT]" if not global_ev_sufficient else ""
            summary = f"evidence scored={len(results)}, high(>=8)={high}, risky(<5)={risky}{ev_tag}"
            return self._finish_trace(state, summary)

        except Exception as e:
            return self._error_trace(state, str(e))

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

    def _passes_hard_constraints(self, product, constraints) -> bool:
        """硬约束判断 — 不满足则直接过滤。

        must_tags 改为软约束: 不匹配不会直接过滤，改为在评分中扣分。
        只有品类完全错误或排除标签命中才硬过滤。
        """
        # 预算硬上限 (超过2倍预算直接过滤)
        if constraints.budget_max and product.base_price > constraints.budget_max * 2:
            return False

        # 品类精确匹配（如果指定了）
        if constraints.category and product.category != constraints.category:
            return False

        # 排除标签: 改为软降权（在评分阶段扣分），不再硬过滤
        # 原因: Router LLM 可能从"也可以不是苹果"误提取 avoid=['苹果']
        #       硬过滤会导致整个品牌消失，软降权更安全
        return True
