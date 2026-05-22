"""V1 Skill Registry — 技能注册与发现。

Skill 是组合能力（编排多个 Tool），Tool 是原子能力。
每个 Skill 定义：输入、输出、所需工具、验证规则。
"""

from typing import Optional
from pydantic import BaseModel, Field


class SkillManifest(BaseModel):
    """技能描述清单"""
    name: str
    description: str
    version: str = "1.0"
    inputs: list[str] = Field(default_factory=list)     # 输入字段名
    outputs: list[str] = Field(default_factory=list)     # 输出字段名
    required_tools: list[str] = Field(default_factory=list)  # 依赖的工具名
    category: str = "general"  # product / review / decision / visual
    priority: int = 50         # 0-100，越高越优先


class SkillRegistry:
    """技能注册中心 — V1 内存实现"""

    def __init__(self):
        self._skills: dict[str, SkillManifest] = {}
        self._register_builtins()

    def _register_builtins(self):
        builtins = [
            SkillManifest(
                name="product_visual_parse",
                description="解析商品截图/包装图，提取品名、品牌、规格、价格等结构化字段",
                version="1.0",
                inputs=["image_url", "user_query"],
                outputs=["product_name", "brand", "category", "specs", "price_estimate", "confidence"],
                required_tools=["qwen_vision", "image_downloader"],
                category="visual",
                priority=80,
            ),
            SkillManifest(
                name="product_retrieve",
                description="多通道商品检索：文本关键词 + 向量相似度 + 品类精确匹配",
                version="1.0",
                inputs=["user_query", "category", "sub_category", "top_k"],
                outputs=["products", "evidence_list"],
                required_tools=["product_text_search", "product_vector_search", "structured_filter"],
                category="product",
                priority=90,
            ),
            SkillManifest(
                name="review_risk_mining",
                description="从用户评论中挖掘风险信号：差评比例、质量问题、安全投诉",
                version="1.0",
                inputs=["product_id", "top_k"],
                outputs=["risk_evidence", "risk_score", "risk_tags"],
                required_tools=["review_search", "risk_analyzer"],
                category="review",
                priority=70,
            ),
            SkillManifest(
                name="policy_check",
                description="查询购物政策、航空携带规则、售后保修条款",
                version="1.0",
                inputs=["user_query", "product_id", "category"],
                outputs=["policy_evidence", "compliance"],
                required_tools=["policy_lookup"],
                category="policy",
                priority=60,
            ),
            SkillManifest(
                name="compatibility_check",
                description="检查设备兼容性：接口、功率、协议、尺寸",
                version="1.0",
                inputs=["product_id", "user_devices"],
                outputs=["compatibility_score", "compatibility_detail"],
                required_tools=["compatibility_rule_query"],
                category="compatibility",
                priority=60,
            ),
            SkillManifest(
                name="decision_score",
                description="7 维加权决策评分：文本匹配 + 评论置信度 + 评分 + 政策合规 + 兼容性 + 多样性 + 风险惩罚",
                version="1.0",
                inputs=["candidate_products", "constraints", "evidence_list"],
                outputs=["decision_results", "score_breakdown", "risk_tags"],
                required_tools=["hard_filter", "decision_score_calculator"],
                category="decision",
                priority=85,
            ),
            SkillManifest(
                name="evidence_sufficiency",
                description="检查检索证据是否充足支撑推荐结论",
                version="1.0",
                inputs=["evidence_list", "intent"],
                outputs=["sufficient", "missing_types", "suggestion"],
                required_tools=[],
                category="verification",
                priority=40,
            ),
            SkillManifest(
                name="demo_replay",
                description="加载预置 Demo Pack 数据回放完整推荐流程",
                version="1.0",
                inputs=["scenario_id"],
                outputs=["products", "evidence_list", "decision_results", "trace_steps", "harness_report"],
                required_tools=["demo_replay_loader"],
                category="demo",
                priority=95,
            ),
        ]
        for s in builtins:
            self._skills[s.name] = s

    def register(self, skill: SkillManifest):
        self._skills[skill.name] = skill

    def get(self, name: str) -> Optional[SkillManifest]:
        return self._skills.get(name)

    def list_all(self) -> list[SkillManifest]:
        return list(self._skills.values())

    def list_by_category(self, category: str) -> list[SkillManifest]:
        return [s for s in self._skills.values() if s.category == category]

    def list_by_tool(self, tool_name: str) -> list[SkillManifest]:
        return [s for s in self._skills.values() if tool_name in s.required_tools]

    def names(self) -> list[str]:
        return list(self._skills.keys())

    def __len__(self):
        return len(self._skills)


# 全局单例
_registry: SkillRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry
