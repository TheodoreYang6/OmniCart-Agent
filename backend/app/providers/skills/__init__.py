"""内置语义技能（PromptSkill）—— Phase 6-B4 首个实装：种草文案。

与 Tool 的边界：Tool 做结构化执行（查库/下单），Skill 做语义生成（人设文案）。
技能经 SkillRegistry（ComponentRegistry 同模式）注册，由 ShopActionAgent 关键词触发。
"""

from __future__ import annotations

from app.framework.registry import ComponentRegistry
from app.framework.skills import PromptSkill, PromptSkillSpec

__all__ = ["ProductCopywriterSkill", "builtin", "get_skill_registry"]


class ProductCopywriterSkill(PromptSkill):
    """种草文案技能：给定商品信息，生成欧米人设的社交种草文案。"""

    spec = PromptSkillSpec(
        name="copywriter.product",
        description="为商品生成小红书风格种草文案（欧米 人设、限定商品事实、不编造参数）",
        capability="chat_generation",
        template=(
            "你是欧米，活泼可爱的AI购物助手。请为下面的商品写一段种草文案：\n"
            "- 3-4 句，口语化带 emoji，突出卖点\n"
            "- 只能使用给定的商品信息，禁止编造参数/价格/功效\n"
            "- 结尾带一句行动号召\n\n"
            "[商品信息]\n{product_info}\n\n文案："
        ),
    )


def builtin() -> list:
    """返回全部内置语义技能实例。"""
    return [ProductCopywriterSkill()]


_registry = None


def get_skill_registry():
    """进程级单例 SkillRegistry（kind="skill"，与 ToolRegistry 同模式装配）。"""
    global _registry
    if _registry is None:
        reg = ComponentRegistry(kind="skill")
        reg.register_all(builtin())
        _registry = reg
    return _registry
