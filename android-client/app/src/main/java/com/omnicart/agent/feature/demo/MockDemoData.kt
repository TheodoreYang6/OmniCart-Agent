package com.omnicart.agent.feature.demo

import com.omnicart.agent.core.model.*

/** 一键演示完整 Demo 数据 — 预置 Evidence/Trace/Harness 全部面板内容。 */
object MockDemoData {

    fun buildDemoProducts(): List<Product> = listOf(
        Product(
            productId = "p_digital_007", title = "Apple AirPods Pro 3 主动降噪真无线蓝牙耳机",
            brand = "Apple", category = "数码电子", subCategory = "真无线耳机", price = 1899.0,
            imageUrls = listOf("/api/products/p_digital_007/image"),
            skus = listOf(Sku("s1", mapOf("颜色" to "白色"), 1899.0), Sku("s2", mapOf("颜色" to "黑色"), 1899.0)),
            ragKnowledge = RagKnowledge(
                marketingDescription = "Apple旗舰TWS，H3芯片，自适应降噪，空间音频",
                userReviews = listOf(ReviewItem("小明", 5, "降噪一流"), ReviewItem("小红", 4, "音质好但贵")),
            ),
        ),
        Product(
            productId = "p_digital_009", title = "华为 FreeBuds Pro 5 主动降噪真无线蓝牙耳机",
            brand = "华为", category = "数码电子", subCategory = "真无线耳机", price = 1499.0,
            imageUrls = listOf("/api/products/p_digital_009/image"),
            skus = listOf(Sku("s1", mapOf("颜色" to "陶瓷白"), 1499.0)),
            ragKnowledge = RagKnowledge(
                marketingDescription = "华为旗舰TWS，静谧通话3.0，Hi-Res认证",
                userReviews = listOf(ReviewItem("Alice", 5, "通话质量极好"), ReviewItem("Bob", 4, "续航不错")),
            ),
        ),
    )

    fun buildDemoDecisions(): List<DecisionResult> = listOf(
        DecisionResult(
            productId = "p_digital_007",
            evidenceIds = listOf("E-MKT-p_digital_007", "R-p_digital_007-0", "R-p_digital_007-1"),
            riskFactors = listOf("价格较高 ¥1899", "仅适配苹果生态"),
            recommendationReason = "Apple旗舰TWS，H3芯片+自适应降噪",
            recommendationLevel = "strong_recommend",
            recommendationScore = RecommendationScore(
                version = "omi_recommendation_v1", score = 91, matchLabel = "高度匹配",
                evidenceLabel = "证据充分", informationStatus = "资料较完整",
                dimensions = listOf(
                    RecommendationScoreDimension("need_fit", "需求契合", 94, "已通过本次需求筛选"),
                    RecommendationScoreDimension("budget_fit", "预算适配", 86, "处于舒适预算区间"),
                    RecommendationScoreDimension("information", "资料完整", 86, "资料较完整"),
                ),
            ),
        ),
        DecisionResult(
            productId = "p_digital_009",
            evidenceIds = listOf("E-MKT-p_digital_009", "R-p_digital_009-0"),
            riskFactors = listOf("部分用户反馈佩戴不稳"),
            recommendationReason = "华为旗舰TWS，Hi-Res认证+静谧通话",
            recommendationLevel = "recommended",
            recommendationScore = RecommendationScore(
                version = "omi_recommendation_v1", score = 77, matchLabel = "较匹配",
                evidenceLabel = "资料较完整", informationStatus = "资料较完整",
                dimensions = listOf(
                    RecommendationScoreDimension("need_fit", "需求契合", 76, "符合主要需求，可作备选"),
                    RecommendationScoreDimension("information", "资料完整", 86, "资料较完整"),
                ),
            ),
        ),
    )

    fun buildDemoEvidence(): List<EvidenceItem> = listOf(
        EvidenceItem("E-MKT-p_digital_007", "marketing", "p_digital_007", "p_digital_007",
            "Apple AirPods Pro 3 采用H3芯片，支持自适应降噪和空间音频，续航6小时，支持MagSafe无线充电", "text", 0.95),
        EvidenceItem("R-p_digital_007-0", "review_positive", "p_digital_007", "p_digital_007",
            "用户小明(5星): 降噪效果一流，地铁上几乎听不到噪音，通透模式也很自然", "text", 0.90),
        EvidenceItem("R-p_digital_007-1", "review_risk", "p_digital_007", "p_digital_007",
            "用户小红(2星): 佩戴久了耳朵会不舒服，左右耳有时断连", "text", 0.70),
        EvidenceItem("POL-flight-001", "policy_faq", "", null,
            "航空携带规则：含锂电池的蓝牙耳机可随身携带，不可托运。单个电池不超过100Wh无需申报", "text", 0.85),
    )

    fun buildDemoTraces(): List<TraceStepItem> = listOf(
        TraceStepItem("T001", "Router Agent (规则+LLM)", "intent_classify", "推荐降噪蓝牙耳机", "intent=recommend, category=数码电子", 12, "success"),
        TraceStepItem("T002", "Retrieval Agent", "text_search", "蓝牙耳机 降噪 top_k=10", "候选商品 3 个", 85, "success"),
        TraceStepItem("T003", "Qwen Reranker", "semantic_rerank", "3 candidates", "reranked, top3 scores: 0.89, 0.86, 0.83", 230, "success"),
        TraceStepItem("T004", "Evidence Sufficiency Checker", "evidence_check", "4 evidence items", "sufficient", 1, "pass"),
        TraceStepItem("T005", "Decision Agent", "hard_filter_and_score", "3 candidates + constraints", "top=AirPods Pro 3, score=0.89", 45, "success"),
        TraceStepItem("T006", "Response Agent (Qwen LLM)", "generate_answer", "compiled context + evidence", "evidence-bound answer generated", 1200, "success"),
        TraceStepItem("T007", "Response Guard", "validate_response", "answer + evidence + scores", "checks: 5/5 passed", 5, "success"),
    )

    fun buildDemoHarness(): Map<String, Any?> = mapOf(
        "schema_valid" to true, "evidence_bound" to true, "score_recalculable" to true,
        "policy_cited" to true, "risk_warning" to true, "sufficiency_check" to true,
        "no_empty_answer" to true,
    )
}
