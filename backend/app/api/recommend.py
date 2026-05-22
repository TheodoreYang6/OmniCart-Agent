import uuid
import time
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.repositories.product_repo import get_product_repo
from app.retrieval.text_retriever import TextRetriever
from app.decision.scoring import DecisionScoring
from app.agents.visual_agent import VisualAgent

router = APIRouter()

_product_repo = get_product_repo()
_retriever = TextRetriever(_product_repo)
_scorer = DecisionScoring()
_visual_agent = VisualAgent()


class RecommendRequest(BaseModel):
    user_query: str
    image_url: Optional[str] = None
    demo_mode: bool = False
    session_id: str = ""


class RecommendResponse(BaseModel):
    session_id: str
    answer: str
    products: list[dict]
    evidence_list: list[dict]
    decision_results: list[dict]
    trace_steps: list[dict]
    visual_result: dict | None
    skill_executions: list
    harness_report: dict
    fallback_status: dict


@router.post("/api/recommend", response_model=RecommendResponse)
async def recommend(req: RecommendRequest):
    session_id = str(uuid.uuid4())[:8]
    trace_steps: list[dict] = []
    visual_result = None

    # ---- Image parse (if provided) ----
    if req.image_url:
        t0 = time.perf_counter()
        visual_result = _visual_agent.parse(req.image_url, req.user_query)
        elapsed = round((time.perf_counter() - t0) * 1000)
        trace_steps.append({
            "step_id": "T001",
            "agent_name": "Visual Agent",
            "action": "visual_parse",
            "input_summary": req.image_url,
            "output_summary": (
                f"product={visual_result.product_name}, "
                f"brand={visual_result.brand}, "
                f"confidence={visual_result.confidence}"
            ),
            "latency_ms": elapsed,
            "status": "success" if visual_result.confidence > 0 else "fallback",
        })
    else:
        trace_steps.append({
            "step_id": "T001",
            "agent_name": "Visual Agent",
            "action": "skipped",
            "input_summary": "no image",
            "output_summary": "no image provided",
            "latency_ms": 0,
            "status": "skipped",
        })

    # ---- Constraint parsing ----
    constraints = _parse_constraints(req.user_query)

    # ---- Retrieve ----
    search_query = req.user_query
    if visual_result and visual_result.product_name:
        search_query = f"{req.user_query} {visual_result.product_name} {visual_result.brand or ''}"

    retrieved = _retriever.search(
        query=search_query,
        top_k=10,
        category=constraints.get("category"),
        sub_category=constraints.get("sub_category"),
        price_max=constraints.get("budget_max"),
        price_min=constraints.get("budget_min"),
    )

    products = []
    decision_results = []
    evidence_list = []

    for item in retrieved:
        product = _product_repo.get_by_id(item["product_id"])
        if product is None:
            continue

        result = _scorer.score(
            product=product,
            query=search_query,
            keyword_score=item.get("score", 0.0),
            budget_max=constraints.get("budget_max"),
            scenario=constraints.get("scenario"),
            visual_result=visual_result,
        )

        products.append(item)
        decision_results.append(result.model_dump())

        for eid in item.get("evidence_ids", []):
            evidence_list.append({
                "evidence_id": eid,
                "source_type": eid.split("-")[0].replace("POL", "policy").replace("R", "review").replace("E", "marketing"),
                "source_id": item["product_id"],
                "product_id": item["product_id"],
                "content": f"Evidence for {item['product_id']}",
                "modality": "text",
                "confidence": min(1.0, item.get("score", 0.0) / 10.0),
            })

    # Add visual evidence
    if visual_result and visual_result.evidence_list:
        for ve in visual_result.evidence_list:
            evidence_list.append({
                "evidence_id": ve.evidence_id,
                "source_type": "visual",
                "source_id": "screenshot",
                "product_id": None,
                "content": f"{ve.field}: {ve.value}",
                "modality": "image",
                "confidence": ve.confidence,
            })

    # Sort by final_score
    paired = list(zip(products, decision_results))
    paired.sort(key=lambda x: x[1]["final_score"], reverse=True)
    products = [p for p, _ in paired]
    decision_results = [d for _, d in paired]

    trace_steps.append({
        "step_id": "T002",
        "agent_name": "V0-TextPipeline",
        "action": "text_retrieve_and_score",
        "input_summary": search_query[:80],
        "output_summary": f"found {len(products)} products",
        "latency_ms": 0,
        "status": "success",
    })

    answer = _build_answer(products[:5], decision_results[:5])

    fallback_status: dict = {"visual_enabled": req.image_url is not None}
    if visual_result:
        fallback_status["visual_level"] = visual_result.fallback_level
        fallback_status["visual_confidence"] = visual_result.confidence
    else:
        fallback_status["visual_enabled"] = False

    return RecommendResponse(
        session_id=session_id,
        answer=answer,
        products=products,
        evidence_list=evidence_list,
        decision_results=decision_results,
        trace_steps=trace_steps,
        visual_result=visual_result.model_dump() if visual_result else None,
        skill_executions=[],
        harness_report={},
        fallback_status=fallback_status,
    )


def _parse_constraints(query: str) -> dict:
    constraints: dict = {}
    query_lower = query.lower()

    # Category detection (Chinese names matching official dataset)
    category_rules = [
        ("数码电子", ["手机", "iphone", "笔记本", "平板", "耳机", "音箱", "手表", "相机", "数码", "电子", "智能"]),
        ("美妆护肤", ["精华", "面霜", "防晒", "洁面", "卸妆", "面膜", "眼霜", "粉底", "口红", "唇釉", "化妆水", "乳液", "眉笔", "美妆", "护肤", "抗初老", "保湿"]),
        ("服饰运动", ["t恤", "短袖", "卫衣", "夹克", "羽绒", "运动鞋", "徒步", "登山", "瑜伽", "背包", "帽子", "户外", "跑步", "健身", "休闲裤", "牛仔裤"]),
        ("食品饮料", ["咖啡", "零食", "坚果", "方便面", "饮料", "牛奶", "巧克力", "饼干", "茶叶", "保健", "维生素", "宠物粮", "猫粮", "狗粮", "调味", "橄榄油"]),
    ]

    for category, keywords in category_rules:
        for kw in keywords:
            if kw in query_lower:
                constraints["category"] = category
                break
        if "category" in constraints:
            break

    # Budget detection
    for price in [5000, 3000, 2000, 1000, 500, 300, 200, 150, 100, 50]:
        if f"{price}元" in query or f"{price}块" in query or f"¥{price}" in query_lower:
            constraints["budget_max"] = float(price)
            break

    # Scenario detection
    for cn, en in [
        ("出差", "business_trip"), ("旅行", "travel"), ("飞机", "flight"),
        ("通勤", "commute"), ("户外", "outdoor"), ("露营", "outdoor"),
        ("游戏", "gaming"), ("办公", "desk"), ("运动", "sport"),
        ("跑步", "running"), ("健身", "fitness"), ("音乐", "music"),
    ]:
        if cn in query:
            constraints["scenario"] = en
            break

    return constraints


# ---- V2 LangGraph Workflow Endpoint ----

@router.post("/api/recommend/v2", response_model=RecommendResponse)
async def recommend_v2(req: RecommendRequest):
    """V2 Agent Workflow: Router → Retrieval → Decision → Response"""
    from app.workflow.graph import run_workflow

    session_id = req.session_id or str(uuid.uuid4())[:8]

    result = await run_workflow(
        user_query=req.user_query,
        image_url=req.image_url,
        session_id=session_id,
    )
    result.session_id = session_id

    return RecommendResponse(
        session_id=session_id,
        answer=result.answer,
        products=result.retrieved_products,
        evidence_list=result.evidence_list,
        decision_results=result.decision_results,
        trace_steps=result.trace_steps,
        visual_result=result.visual_result,
        skill_executions=result.skill_executions,
        harness_report=result.harness_report,
        fallback_status=result.fallback_status,
    )


def _build_answer(products: list[dict], results: list[dict]) -> str:
    if not products:
        return "抱歉，没有找到符合您条件的商品。请尝试调整需求。"

    lines = ["根据您的需求，为您找到以下商品："]
    for i, (p, r) in enumerate(zip(products, results), 1):
        score = r.get("display_score", 0)
        cat_tag = f"[{p.get('category', '')}/{p.get('sub_category', '')}]"
        lines.append(f"\n{i}. {cat_tag} {p['title']} - ¥{p['price']}")
        lines.append(f"   推荐分 {score}/10")
        reason = r.get("recommendation_reason", "")
        if reason:
            lines.append(f"   {reason}")
        risks = r.get("risk_factors", [])
        if risks:
            lines.append(f"   ⚠ {', '.join(risks)}")

    return "\n".join(lines)
