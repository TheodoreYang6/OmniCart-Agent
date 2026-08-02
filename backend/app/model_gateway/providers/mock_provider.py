"""Mock ModelProvider —— 逐字节复现 gateway 原内联 MOCK 分支，保证 Mock 模式行为不变。"""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.model_gateway.mock_model import MockChat, MockEmbedding


class MockModelProvider:
    """无 API Key 的本地 Mock 实现。"""

    is_mock = True

    async def chat(self, *, model: str, prompt: str, system: str, temperature: float, max_tokens: int) -> str:
        return MockChat().generate(prompt, system)

    async def chat_stream(
        self, *, model: str, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> AsyncIterator[str]:
        for ch in MockChat().generate(prompt, system):
            yield ch

    async def chat_with_tools(self, *, model: str, messages: list[dict], tools: list[dict],
                              system: str, temperature: float, max_tokens: int) -> dict:
        """MOCK 确定性脚本（OmniAgent Loop 可演示/可测）：

        - 已有 tool 结果回填 → 结束循环（空 tool_calls + 结论 content）；
        - 首轮且消息含商品词 → 返回 shopping.search 调用；
        - 其余 → 惰性空结果（单轮工具选择器等旧语义不变）。
        """
        has_tool_result = any(m.get("role") == "tool" for m in messages)
        if has_tool_result:
            return {"content": "mock: 信息已收集完整，可以回答了", "tool_calls": []}
        last_user = next((m.get("content", "") for m in reversed(messages)
                          if m.get("role") == "user"), "")
        tool_names = {t.get("function", {}).get("name") for t in tools}
        # QU V2：首条消息带子目标提示 → 模拟 LLM 逐目标发多个 search 调用（拆分场景可演示）
        if "shopping.search" in tool_names and "子目标：" in last_user:
            import re

            m = re.search(r"子目标：([^（\n]+)", last_user)
            roles = [r.strip() for r in (m.group(1).split("/") if m else []) if r.strip()]
            if roles:
                return {"content": "", "tool_calls": [
                    {"id": f"mock_call_{i}", "name": "shopping.search",
                     "args": {"query": r, "top_k": 4}}
                    for i, r in enumerate(roles[:5], 1)]}
        product_words = ("耳机", "手机", "推荐", "商品", "精华", "面霜", "跑鞋", "零食")
        if "shopping.search" in tool_names and any(w in last_user for w in product_words):
            query = last_user.split("[用户消息]")[-1].strip().splitlines()[-1][:30]
            # 模拟真实 LLM 提炼检索词：剥口语前缀，只留商品词干
            for noise in ("推荐一款", "推荐一个", "推荐", "帮我找", "我想买", "来一款", "来个"):
                query = query.replace(noise, "")
            query = query.strip(" ，,。～~！!")
            return {"content": "", "tool_calls": [{
                "id": "mock_call_1", "name": "shopping.search",
                "args": {"query": query or "商品", "top_k": 5},
            }]}
        return {"content": "", "tool_calls": []}

    async def embed(self, *, texts: list[str], model: str, dimensions: int,
                    is_query: bool = False) -> list[list[float]]:
        # MOCK 忽略 is_query（确定性哈希向量与查询/文档无关）
        return MockEmbedding().embed(texts)

    async def vision(
        self,
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        prompt: str,
        system: str,
        image_path: str | None,
        image_bytes: bytes | None,
        content_type: str,
        image_info: str,
    ) -> str:
        return MockChat().generate(f"[Mock Vision] image={image_info}. prompt: {prompt}", system)

    async def rerank(self, *, query: str, documents: list[str], model: str, top_n: int) -> list[dict]:
        return [
            {"index": i, "document": d, "relevance_score": 1.0 - i * 0.05}
            for i, d in enumerate(documents[: top_n or 10])
        ]

    async def health_check(self) -> bool:
        return True
