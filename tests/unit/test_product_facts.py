from app.schemas.product import FaqItem, Product, RagKnowledge, ReviewItem
import pytest

from app.retrieval.discovery_retriever import DiscoveryRetriever
from app.schemas.discovery_document import build_discovery_document, build_evidence_documents
from app.services.product_facts import build_discovery_text, extract_product_facts, filter_products_by_facts


def _food(pid: str, title: str, description: str, faq_answer: str = "配料信息见包装") -> Product:
    return Product(product_id=pid, title=title, brand="测试", category="食品饮料",
                   sub_category="饮料", base_price=10,
                   rag_knowledge=RagKnowledge(marketing_description=description,
                                              official_faq=[FaqItem(question="配料", answer=faq_answer)],
                                              user_reviews=[ReviewItem(nickname="A", rating=5, content="喝完瘦了")]))


def test_facts_only_use_catalog_sources_not_review_outcomes():
    product = _food("tea", "无糖茶", "0糖0卡0脂，适合日常控卡。", "0糖0脂")
    facts = extract_product_facts(product)
    assert {f.fact_key for f in facts} >= {"nutrition.zero_sugar", "nutrition.zero_fat", "nutrition.zero_calorie"}
    assert all("瘦了" not in f.source_text for f in facts)
    assert "0糖" in build_discovery_text(product, facts)


def test_food_facts_hard_filter_keeps_light_food_and_excludes_unknown_food():
    light = _food("light", "0糖茶", "0糖0脂冷泡茶")
    unknown = _food("unknown", "普通果汁", "果味饮料")
    kept, report = filter_products_by_facts([light, unknown], "想喝点低糖的，不想长胖")
    assert [p.product_id for p in kept] == ["light"]
    assert report["applied"] and report["light_request"]


@pytest.mark.asyncio
async def test_discovery_nutrition_constraint_never_returns_non_food_catalog_items(monkeypatch):
    """A food constraint must not be satisfied by an unrelated non-food item."""
    from app.retrieval import discovery_retriever

    light = _food("light", "0糖茶", "0糖0脂冷泡茶")
    non_food = Product(product_id="phone", title="0糖手机壳", brand="测试", category="数码电子",
                       sub_category="配件", base_price=20)

    class Repo:
        def list_all(self):
            return [light, non_food]

    monkeypatch.setattr(discovery_retriever, "USE_DISCOVERY_V8", False)
    found, report = await DiscoveryRetriever(Repo()).search("我想喝低糖饮料")
    assert [p["product_id"] for p in found] == ["light"]
    assert report["applied"]


@pytest.mark.asyncio
async def test_discovery_prefers_persisted_fact_rows_for_final_eligibility(monkeypatch):
    """After backfill, PostgreSQL fact rows are the hard-filter authority."""
    from app.retrieval import discovery_retriever

    light = _food("light", "0糖茶", "0糖0脂冷泡茶")

    class Repo:
        def list_all(self):
            return [light]

    class Facts:
        async def facts_for_products(self, _ids):
            # Simulate an old/incomplete row set: it must not be silently
            # replaced with freshly inferred facts during production filtering.
            return {"light": [{"product_id": "light", "fact_key": "nutrition.low_fat", "source_text": "0脂"}]}

    monkeypatch.setattr(discovery_retriever, "USE_DISCOVERY_V8", False)
    retriever = DiscoveryRetriever(Repo())
    retriever._fact_repo = Facts()
    found, report = await retriever.search("我想喝低糖饮料")
    assert found == []
    assert report["fact_source"] == "postgres"


def test_v8_discovery_card_excludes_marketing_and_reviews_but_evidence_keeps_them():
    product = _food("tea", "无糖茶", "营销文案：低糖茶适合通勤", "官方问答：不添加蔗糖")
    doc = build_discovery_document(product)
    evidence = build_evidence_documents(product)
    assert "营销文案" not in doc.text
    assert "喝完瘦了" not in doc.text
    assert {item.source_type for item in evidence} >= {"marketing", "faq", "review"}
    assert all(item.payload.get("content") == item.text for item in evidence)
