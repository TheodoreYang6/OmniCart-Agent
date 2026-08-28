import asyncio
from types import SimpleNamespace

from app.context.conversation_assembler import ConversationContextAssembler
from app.schemas.workflow import Constraints, WorkflowState
from app.services.recommendation_brief import build_recommendation_brief


def _product(pid: str) -> dict:
    return {"product_id": pid, "title": f"商品{pid}", "brand": "欧米", "price": 199}


def test_answer_context_keeps_current_contract_and_primary_only():
    state = WorkflowState(
        user_query="第二款便宜一点",
        intent="alternative",
        constraints=Constraints(category="数码电子", budget_max=300, exclude_tags=["入耳式"]),
        retrieved_products=[{**_product("p1"), "filter_bucket": "primary", "evidence_types": ["facts"]},
                            {**_product("p2"), "filter_bucket": "alternative", "evidence_types": ["faq"]}],
        decision_results=[
            {"product_id": "p1", "recommendation_level": "recommended", "evidence_confidence": .8,
             "recommendation_reason": "价格合适", "risk_factors": []},
            {"product_id": "p2", "recommendation_level": "recommended", "evidence_confidence": .8,
             "recommendation_reason": "也可考虑", "risk_factors": []},
        ],
        evidence_list=[
            {"product_id": "p1", "content": "已核对价格和规格"},
            {"product_id": "p2", "content": "不应成为首选依据"},
        ],
        answer_draft="这是 scratchpad，不能进入最终上下文",
        context_prompt="[工具结果] 不能进入最终上下文",
        structured_retrieval_report={"version": "v9"},
    )
    build_recommendation_brief(state)
    context = asyncio.run(ConversationContextAssembler().assemble(state))

    assert "第二款便宜一点" in context.text
    assert "预算上限=300元" in context.text
    assert "[工具结果]" not in context.text
    assert "scratchpad" not in context.text
    assert "p1" in context.text
    assert "p2" not in context.text  # evidence and product delivery only include locked primary
    assert "回答覆盖要求：本轮有 1 款首选" in context.text
    assert context.manifest["version"] == "answer_context_v1"


def test_answer_context_uses_compact_product_name_not_marketing_tail():
    state = WorkflowState(
        user_query="通勤降噪耳机",
        retrieved_products=[{
            "product_id": "p1", "brand": "漫步者",
            "title": "漫步者W820NB Plus头戴式主动降噪耳机超长续航40小时蓝牙5.3深灰配色",
            "price": 299,
        }],
        primary_product_ids=["p1"],
        recommendation_brief=[{"product_id": "p1", "why_it_fits": "适合通勤", "caution": "以详情为准"}],
    )
    context = asyncio.run(ConversationContextAssembler().assemble(state))

    assert "漫步者 W820NB Plus头戴式主动降噪耳机" in context.text
    assert "超长续航40小时蓝牙5.3深灰配色" not in context.text


def test_answer_context_budget_never_drops_current_request():
    state = WorkflowState(user_query="我要给妈妈挑一份生日礼物", intent="gift")
    state.used_memories = [{"content": "偏好" * 400}]
    context = asyncio.run(ConversationContextAssembler().assemble(state))

    assert "我要给妈妈挑一份生日礼物" in context.text
    assert context.manifest["tokens"] <= context.manifest["budget"]


def test_answer_context_keeps_recommendations_before_history_under_budget_pressure(monkeypatch):
    state = WorkflowState(
        user_query="给我挑一款通勤耳机",
        retrieved_products=[_product("p1")],
        primary_product_ids=["p1"],
        recommendation_brief=[{"product_id": "p1", "why_it_fits": "适合通勤", "caution": "核对佩戴"}],
    )
    assembler = ConversationContextAssembler()
    monkeypatch.setattr(
        ConversationContextAssembler, "_recent_turns", staticmethod(lambda *_: "旧对话" * 1000)
    )
    monkeypatch.setattr(
        ConversationContextAssembler, "_tokens",
        staticmethod(lambda text: 4000 if "最近完整对话" in text else 100),
    )

    context = asyncio.run(assembler.assemble(state))
    status = {item["section"]: item for item in context.manifest["sections"]}
    assert status["recommendations"]["included"] is True
    assert status["history"]["included"] is False
    assert "p1" in context.text
    assert context.manifest["sources"]["recommendations"]["primary_product_ids"] == ["p1"]


def test_answer_context_does_not_repeat_messages_already_covered_by_checkpoint():
    messages = [
        SimpleNamespace(message_id="m1", role="user", content="旧问题"),
        SimpleNamespace(message_id="m2", role="assistant", content="旧回答"),
        SimpleNamespace(message_id="m3", role="user", content="新的追问"),
    ]

    remaining = ConversationContextAssembler._messages_after_checkpoint(
        messages, {"source_through_message_id": "m2"}
    )

    assert [message.message_id for message in remaining] == ["m3"]


def test_answer_context_reads_locked_dossier_from_state_not_tool_prompt():
    state = WorkflowState(
        user_query="问欧米这件商品值不值得买",
        focus_product_id="p1",
        context_prompt="[单品深度档案] 这段工具转录绝不能进入最终回答",
        product_dossiers={
            "p1": {
                "product_id": "p1", "brand": "欧米", "title": "通勤耳机", "price": 299,
                "evidence_status": "证据充分", "marketing_description": "支持主动降噪和多设备连接",
                "skus": [
                    {"sku_id": "s1", "properties": {"颜色": "黑色"}, "price": 299},
                    {"sku_id": "s2", "properties": {"颜色": "银色"}, "price": 329},
                ], "price_range": {"min": 299, "max": 329},
                "review_summary": {"count": 20, "avg_rating": 4.6, "positive_count": 16, "risk_count": 2},
                "official_faq": [{"question": "能否连接电脑", "answer": "支持蓝牙连接"}],
                "information_gaps": ["佩戴体验因人而异"],
            }
        },
    )

    context = asyncio.run(ConversationContextAssembler().assemble(state))

    assert "通勤耳机" in context.text
    assert "支持主动降噪" in context.text
    assert "颜色:黑色＝¥299" in context.text
    assert "规格和价格必须按上述一一对应" in context.text
    assert "只分析这件已锁定商品" in context.text
    assert "工具转录绝不能" not in context.text


def test_answer_context_keeps_multi_target_group_identity():
    state = WorkflowState(
        user_query="给我各挑一款零食和饮品",
        retrieved_products=[
            {**_product("snack"), "group_role": "零食"},
            {**_product("drink"), "group_role": "饮品"},
        ],
        primary_product_ids=["snack", "drink"],
        recommendation_brief=[
            {"product_id": "snack", "why_it_fits": "适合解馋", "caution": "留意配料"},
            {"product_id": "drink", "why_it_fits": "适合日常喝", "caution": "留意口味"},
        ],
        retrieval_groups=[
            {"role": "零食", "status": "matched", "product_ids": ["snack"]},
            {"role": "饮品", "status": "matched", "product_ids": ["drink"]},
        ],
    )
    context = asyncio.run(ConversationContextAssembler().assemble(state))
    assert "[零食] [snack]" in context.text
    assert "[饮品] [drink]" in context.text


def test_answer_context_exposes_missing_group_instead_of_silently_relabeling_products():
    state = WorkflowState(
        user_query="零食和饮品各挑一款",
        retrieved_products=[_product("snack")],
        primary_product_ids=["snack"],
        recommendation_brief=[{"product_id": "snack", "why_it_fits": "适合解馋", "caution": "留意配料"}],
        retrieval_groups=[
            {"role": "零食", "status": "matched", "product_ids": ["snack"]},
            {"role": "饮品", "status": "missing", "product_ids": [], "missing_reason": "未找到低负担饮品"},
        ],
    )
    context = asyncio.run(ConversationContextAssembler().assemble(state))
    assert "缺少 [饮品]：未找到低负担饮品" in context.text
    assert "不能把其他分组商品说成它的替代" in context.text
