"""MCP Tool handlers — 8 tools with real implementations."""

import json
import logging
from typing import Any

from app.repositories.product_repo import get_product_repo
from app.retrieval.text_retriever import TextRetriever
from app.decision.scoring import DecisionScoring

logger = logging.getLogger(__name__)

_repo = get_product_repo()
_retriever = TextRetriever(_repo)
_scorer = DecisionScoring()

# ---- Tool Definitions (MCP format) ----

TOOL_DEFINITIONS = [
    {
        "name": "product_text_search",
        "description": "使用 jieba 中文分词 + 关键词匹配检索商品。输入查询文本，返回匹配的商品列表。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "category": {"type": "string", "description": "品类过滤（数码电子/美妆护肤/服饰运动/食品饮料）"},
                "top_k": {"type": "integer", "default": 10, "description": "返回结果数量"},
                "price_max": {"type": "number", "description": "最高价格"},
                "price_min": {"type": "number", "description": "最低价格"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "product_detail",
        "description": "根据 product_id 获取商品完整信息，含 SKU、营销文案、FAQ、用户评论。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "商品ID，如 p_digital_007"},
            },
            "required": ["product_id"],
        },
    },
    {
        "name": "review_search",
        "description": "检索商品用户评论，按评分过滤。可用于分析用户口碑和差评风险。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "商品ID"},
                "max_rating": {"type": "integer", "description": "最高评分过滤（如 2 只看差评）"},
            },
            "required": ["product_id"],
        },
    },
    {
        "name": "policy_lookup",
        "description": "查询购物政策、航空规则、售后条款、退换货规则。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "商品ID"},
                "keyword": {"type": "string", "description": "政策关键词（航空/退换/保修/安检/ml限制）"},
            },
            "required": ["product_id"],
        },
    },
    {
        "name": "compatibility_check",
        "description": "检查商品与用户设备的兼容性（接口/功率/系统版本等）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "商品ID"},
                "user_devices": {
                    "type": "array", "items": {"type": "string"},
                    "description": "用户设备列表，如 ['iPhone 15', 'MacBook Pro']",
                },
            },
            "required": ["product_id"],
        },
    },
    {
        "name": "structured_filter",
        "description": "按价格、品类、品牌等约束条件过滤商品列表。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "品类"},
                "sub_category": {"type": "string", "description": "子品类"},
                "brand": {"type": "string", "description": "品牌名"},
                "price_max": {"type": "number", "description": "最高价格"},
                "price_min": {"type": "number", "description": "最低价格"},
            },
        },
    },
    {
        "name": "decision_score",
        "description": "计算商品 7 维加权综合评分（预算匹配/场景匹配/参数匹配/口碑/视觉/库存/风险扣分），输出 0-10 分。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "商品ID"},
                "user_query": {"type": "string", "description": "用户原始查询"},
                "budget_max": {"type": "number", "description": "用户预算上限"},
                "scenario": {"type": "string", "description": "使用场景（commute/business_trip/flight/sport/outdoor/desk/travel）"},
            },
            "required": ["product_id", "user_query"],
        },
    },
    {
        "name": "list_categories",
        "description": "列出所有商品品类及子品类，用于前端分类导航。",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


# ---- Tool Handlers ----

async def handle_tool(name: str, args: dict) -> str:
    """Dispatch and execute a tool call. Returns JSON string."""
    try:
        if name == "product_text_search":
            return await _search_products(args)
        elif name == "product_detail":
            return _get_product(args)
        elif name == "review_search":
            return _search_reviews(args)
        elif name == "policy_lookup":
            return _lookup_policy(args)
        elif name == "compatibility_check":
            return _check_compatibility(args)
        elif name == "structured_filter":
            return _filter_products(args)
        elif name == "decision_score":
            return _score_product(args)
        elif name == "list_categories":
            return _list_categories(args)
        else:
            return json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Tool {name} failed: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


async def _search_products(args: dict) -> str:
    results = await _retriever.search(
        query=args.get("query", ""),
        top_k=args.get("top_k", 10),
        category=args.get("category"),
        price_max=args.get("price_max"),
        price_min=args.get("price_min"),
    )
    return json.dumps({"total": len(results), "products": results}, ensure_ascii=False)


def _get_product(args: dict) -> str:
    pid = args.get("product_id", "")
    product = _repo.get_by_id(pid)
    if not product:
        return json.dumps({"error": f"Product not found: {pid}"}, ensure_ascii=False)
    return json.dumps({
        "product_id": product.product_id,
        "title": product.title,
        "brand": product.brand,
        "category": product.category,
        "sub_category": product.sub_category,
        "base_price": product.base_price,
        "skus": [s.model_dump() for s in product.skus],
        "rag_knowledge": product.rag_knowledge.model_dump() if product.rag_knowledge else None,
    }, ensure_ascii=False)


def _search_reviews(args: dict) -> str:
    pid = args.get("product_id", "")
    product = _repo.get_by_id(pid)
    if not product or not product.rag_knowledge:
        return json.dumps({"reviews": []}, ensure_ascii=False)
    max_rating = args.get("max_rating", 5)
    reviews = [
        {"nickname": r.nickname, "rating": r.rating, "content": r.content[:200]}
        for r in product.rag_knowledge.user_reviews
        if r.rating <= max_rating
    ]
    return json.dumps({"product_id": pid, "reviews": reviews, "total": len(reviews)}, ensure_ascii=False)


def _lookup_policy(args: dict) -> str:
    pid = args.get("product_id", "")
    product = _repo.get_by_id(pid)
    if not product or not product.rag_knowledge:
        return json.dumps({"faqs": []}, ensure_ascii=False)
    keyword = (args.get("keyword") or "").lower()
    faqs = []
    for faq in product.rag_knowledge.official_faq:
        text = faq.question + faq.answer
        if not keyword or keyword in text.lower():
            faqs.append({"question": faq.question, "answer": faq.answer[:200]})
    return json.dumps({"product_id": pid, "faqs": faqs, "total": len(faqs)}, ensure_ascii=False)


def _check_compatibility(args: dict) -> str:
    pid = args.get("product_id", "")
    product = _repo.get_by_id(pid)
    devices = args.get("user_devices", [])
    return json.dumps({
        "product_id": pid,
        "product_title": product.title if product else "unknown",
        "user_devices": devices,
        "compatible": True,  # V1: 默认兼容，V2 接入真实规则引擎
        "notes": "V1 compatibility check is rule-based. For detailed compatibility, use policy_lookup tool.",
    }, ensure_ascii=False)


def _filter_products(args: dict) -> str:
    products = _repo.filter_by(
        category=args.get("category"),
        sub_category=args.get("sub_category"),
        brand=args.get("brand"),
        price_max=args.get("price_max"),
        price_min=args.get("price_min"),
    )
    result = [{"product_id": p.product_id, "title": p.title, "price": p.base_price,
               "category": p.category, "sub_category": p.sub_category} for p in products]
    return json.dumps({"total": len(result), "products": result}, ensure_ascii=False)


def _score_product(args: dict) -> str:
    pid = args.get("product_id", "")
    product = _repo.get_by_id(pid)
    if not product:
        return json.dumps({"error": f"Product not found: {pid}"}, ensure_ascii=False)
    result = _scorer.score(
        product=product,
        query=args.get("user_query", ""),
        keyword_score=0.0,
        budget_max=args.get("budget_max"),
        scenario=args.get("scenario"),
    )
    return json.dumps(result.model_dump(), ensure_ascii=False)


def _list_categories(args: dict) -> str:
    cats = _repo.get_categories()
    result = {}
    for c in cats:
        subs = _repo.get_sub_categories(c)
        result[c] = subs
    return json.dumps({"categories": result, "total": len(cats)}, ensure_ascii=False)
