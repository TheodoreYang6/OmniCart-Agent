"""单品深度档案工具：可信主体、证据与工作流状态回流。"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.framework.tools import ToolContext
from app.providers.tools.shopping import ProductDossierTool
from app.schemas.product import FaqItem, Product, RagKnowledge, ReviewItem, Sku
from app.schemas.workflow import WorkflowState


def _product() -> Product:
    return Product(
        product_id="P-IPHONE-15", title="iPhone 15", brand="Apple 苹果",
        category="数码电子", sub_category="手机", base_price=5999,
        image_path="2_数码电子/images/p_iphone_15.jpg",
        skus=[Sku(sku_id="128", properties={"容量": "128GB"}, price=5999)],
        rag_knowledge=RagKnowledge(
            marketing_description="轻巧机身，配备高分辨率摄像头。",
            official_faq=[FaqItem(question="支持双卡吗？", answer="支持双卡。")],
            user_reviews=[
                ReviewItem(nickname="小王", rating=5, content="拍照很好，续航够一天。"),
                ReviewItem(nickname="小李", rating=2, content="容量对我来说不够用。"),
            ],
        ),
    )


@pytest.mark.asyncio
async def test_dossier_writes_single_product_state_and_evidence():
    product = _product()
    state = WorkflowState(
        user_query="这款怎么样", focus_product_id=product.product_id,
        retrieval_scope="exact_product", resolved_product_ids=[product.product_id],
    )

    async def no_decision(_self, current):
        return current

    repo = SimpleNamespace(get_by_id=lambda pid: product if pid == product.product_id else None)
    with patch("app.repositories.product_repo.get_product_repo", return_value=repo), \
         patch("app.agents.decision_agent.DecisionAgent.execute", new=no_decision):
        result = await ProductDossierTool().run(
            ToolContext(user_id="u", state=state), product_id=product.product_id, focus="reviews",
        )

    assert result.ok
    assert state.retrieved_products[0]["product_id"] == product.product_id
    assert state.retrieved_products[0]["image_urls"] == ["/api/products/P-IPHONE-15/image"]
    assert state.selected_products[0]["product_id"] == product.product_id
    dossier = state.product_dossiers[product.product_id]
    assert dossier["review_summary"]["positive_count"] == 1
    assert dossier["review_summary"]["risk_count"] == 1
    assert any(item["source_type"] == "official_faq" for item in state.evidence_list)
    assert any(item["source_type"] == "user_review_risk" for item in state.evidence_list)
    # 档案保留在结构化请求状态，最终 AnswerContext 再按预算消费；不能把工具
    # 转录塞进 context_prompt。
    assert not state.context_prompt
    assert dossier["title"] == "iPhone 15"


@pytest.mark.asyncio
async def test_dossier_rejects_product_outside_locked_scope():
    state = WorkflowState(focus_product_id="P-LOCKED", resolved_product_ids=["P-LOCKED"])
    result = await ProductDossierTool().run(
        ToolContext(user_id="u", state=state), product_id="P-OTHER",
    )
    assert not result.ok
    assert "锁定范围" in result.message
    assert not state.product_dossiers


@pytest.mark.asyncio
async def test_dossier_cannot_collapse_a_multi_product_recommendation():
    state = WorkflowState(
        retrieved_products=[{"product_id": "P-IPHONE-15"}],
        retrieval_groups=[{"group_id": "g1", "role": "手机", "status": "matched", "product_ids": ["P-IPHONE-15"]}],
    )
    result = await ProductDossierTool().run(ToolContext(state=state), product_id="P-IPHONE-15")
    assert not result.ok
    assert "单一主体" in result.message


@pytest.mark.asyncio
async def test_dossier_marks_missing_sources_as_limited_information():
    product = Product(
        product_id="P-EMPTY", title="空数据商品", brand="测试", category="数码电子", base_price=1,
    )
    state = WorkflowState(focus_product_id="P-EMPTY", resolved_product_ids=["P-EMPTY"])

    async def no_decision(_self, current):
        return current

    repo = SimpleNamespace(get_by_id=lambda pid: product if pid == "P-EMPTY" else None)
    with patch("app.repositories.product_repo.get_product_repo", return_value=repo), \
         patch("app.agents.decision_agent.DecisionAgent.execute", new=no_decision):
        result = await ProductDossierTool().run(ToolContext(state=state), product_id="P-EMPTY")

    assert result.ok
    dossier = state.product_dossiers["P-EMPTY"]
    assert dossier["evidence_status"] == "信息有限"
    assert {"缺少商品说明", "暂无官方问答", "暂无用户评价"}.issubset(dossier["information_gaps"])


def test_dossier_prompt_contract_is_present():
    from app.prompts.agent_prompts import build_omni_agent_prompt

    prompt = build_omni_agent_prompt()
    assert "shopping.product_dossier" in prompt
    assert "[已锁定商品]" in prompt
