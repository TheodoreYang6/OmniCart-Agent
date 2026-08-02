"""Prompt-based skill（语义技能）框架层，区别于 ``app.framework.tools``（可执行工具）。

内置技能见 ``app.providers.skills``；可执行的 function-calling 能力见 ``app.framework.tools``。
"""

from app.framework.skills.protocols import PromptSkill, PromptSkillSpec

__all__ = ["PromptSkill", "PromptSkillSpec"]
