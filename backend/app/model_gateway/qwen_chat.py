import json
import httpx
from typing import AsyncGenerator
from app.core.config import QWEN_API_KEY, QWEN_BASE_URL

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
    return _client


class QwenChat:
    def __init__(self, model: str = "qwen-plus", temperature: float = 0.7, max_tokens: int = 2048):
        self._api_key = QWEN_API_KEY
        self._base_url = QWEN_BASE_URL.rstrip("/")
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def _build_messages(self, prompt: str, system: str = "") -> list[dict]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    async def generate(self, prompt: str, system: str = "") -> str:
        messages = self._build_messages(prompt, system)
        client = _get_client()
        resp = await client.post(
            f"{self._base_url}/services/aigc/text-generation/generation",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model,
                "input": {"messages": messages},
                "parameters": {
                    "temperature": self._temperature,
                    "max_tokens": self._max_tokens,
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["output"]["text"]

    async def generate_stream(self, prompt: str, system: str = "") -> AsyncGenerator[str, None]:
        """流式生成 — 每个 token 到达即 yield。"""
        messages = self._build_messages(prompt, system)
        client = _get_client()
        async with client.stream(
            "POST",
            f"{self._base_url}/services/aigc/text-generation/generation",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model,
                "input": {"messages": messages},
                "parameters": {
                    "temperature": self._temperature,
                    "max_tokens": self._max_tokens,
                    "incremental_output": True,
                },
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if not data_str:
                    continue
                try:
                    chunk = json.loads(data_str)
                    text = chunk.get("output", {}).get("text", "")
                    if text:
                        yield text
                except (json.JSONDecodeError, KeyError):
                    pass
