from types import SimpleNamespace

from app.services.product_entity_eval_cases import ENTITY_EVAL_CASES
from app.services.product_entity_resolver import (
    _product_dict,
    _iphone_fields,
    build_identity_record,
    identity_forms,
    normalize_identity,
)


def test_entity_benchmark_has_at_least_sixty_cases():
    assert len(ENTITY_EVAL_CASES) >= 60
    assert {case["group"] for case in ENTITY_EVAL_CASES} >= {
        "iphone_line",
        "iphone_generation",
        "iphone_model",
        "visual_entity",
        "focused_product",
    }


def test_identity_normalization_handles_spelling_spacing_and_chinese_aliases():
    apple15 = chr(0x82F9) + chr(0x679C) + " 15"
    ai_feng = chr(0x7231) + chr(0x75AF) + "15 Pro"
    assert normalize_identity(" iPhone 15-Pro ") == "iphone15pro"
    assert normalize_identity(apple15) == "apple15"
    assert normalize_identity(ai_feng) == "iphone15pro"
    assert _iphone_fields(apple15)[1] == "iphone"
    assert _iphone_fields(ai_feng)[3] == "iphone15pro"
    assert "iphone15pro" in identity_forms("15pro" + chr(0x82F9) + chr(0x679C) + chr(0x624B) + chr(0x673A))


def test_generated_aliases_include_family_and_variant_identity_only():
    product = SimpleNamespace(
        product_id="p_iphone",
        brand="Apple",
        title="iPhone 15 Pro",
        skus=[{"properties": {"storage": "256GB", "color": "blue"}}],
    )
    identity, aliases = build_identity_record(product)
    normalized = {normalize_identity(value): kind for value, kind in aliases}
    assert identity["product_line_key"] == "iphone"
    assert identity["family_key"] == "apple:iphone:15:pro"
    assert normalized["iphone"] == "product_line"
    assert normalized["iphone15"] == "model"
    assert normalized["iphone15pro"] == "model"
    assert "iphone15pro256gbblue" in normalized


def test_identity_result_exposes_image_api_instead_of_dataset_path():
    product = SimpleNamespace(
        product_id="P-IPHONE-15",
        title="iPhone 15",
        brand="Apple",
        category="数码电子",
        sub_category="手机",
        base_price=5999,
        image_path="2_数码电子/images/p_iphone_15.jpg",
        skus=[],
        rag_knowledge={},
    )
    result = _product_dict(product)
    assert result["image_urls"] == ["/api/products/P-IPHONE-15/image"]
    assert result["image_path"] == "2_数码电子/images/p_iphone_15.jpg"
