"""Prompt-based Skill（语义技能）契约（Phase 6-B4 实装）。

区别于 ``app.framework.tools``（可执行的 function-calling 工具）：
Skill 指基于自然语言 prompt 模板 / 行为模式的能力（业界如 Semantic Kernel 的
semantic function、Anthropic Agent Skills 的指令型能力）。
run() 默认实现：渲染模板 → 调 model_gateway → 返回补全文本。
"""

from __future__ import annotations

from pydantic import BaseModel

__all__ = ["PromptSkillSpec", "PromptSkill"]


class PromptSkillSpec(BaseModel):
    """语义技能契约（prompt-based）。"""

    name: str
    description: str = ""
    template: str = ""                    # prompt 模板（可含 {占位符}）
    capability: str = "chat_generation"   # model_gateway 能力名
    kind: str = "prompt"


class PromptSkill:
    """prompt-based 技能基类 —— run() 渲染模板并调用 model_gateway。

    子类只需声明 ``spec``；需要前置/后置处理时覆写 run()。
    渲染缺占位符时抛 KeyError（调用方负责降级，对齐 Python format 坑的既有经验）。
    """

    spec: PromptSkillSpec

    @property
    def name(self) -> str:
        """供 ComponentRegistry 按名注册（与 Tool 同模式）。"""
        return self.spec.name

    async def run(self, **kwargs) -> str:
        from app.model_gateway.gateway import get_model_gateway

        prompt = self.spec.template.format(**kwargs)
        return await get_model_gateway().chat(self.spec.capability, prompt)
