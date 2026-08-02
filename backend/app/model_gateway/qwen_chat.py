"""Qwen/DeepSeek Chat — OpenAI 兼容协议 (/chat/completions)。

采用 OpenAI 兼容模式而非 DashScope 原生协议，原因：
- 公共云与专属 MaaS 实例均支持兼容模式，原生协议在部分专属实例上不可用
  （返回 InvalidParameter: url error）
- 兼容地址从 QWEN_BASE_URL 派生：.../api/v1 → .../compatible-mode/v1

多提供商路由：模型名以 deepseek 开头时走 DEEPSEEK_BASE_URL/KEY（同为 OpenAI 兼容），
关闭思考的参数按提供商适配（Qwen: enable_thinking；DeepSeek: thinking.type=disabled）。
"""

import json
from typing import AsyncGenerator

import httpx

from app.core.config import QWEN_API_KEY, QWEN_BASE_URL, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
    return _client


def _compat_base() -> str:
    """DashScope 原生地址 → OpenAI 兼容地址。"""
    base = QWEN_BASE_URL.rstrip("/")
    if base.endswith("/api/v1"):
        return base[: -len("/api/v1")] + "/compatible-mode/v1"
    if "/compatible-mode/v1" in base:
        return base
    return base + "/compatible-mode/v1"


class QwenChat:
    def __init__(self, model: str = "qwen-plus", temperature: float = 0.7, max_tokens: int = 2048):
        # deepseek* 模型名 → DeepSeek 端点（OpenAI 兼容）；其余仍走 Qwen
        self._is_deepseek = model.lower().startswith("deepseek")
        if self._is_deepseek:
            self._api_key = DEEPSEEK_API_KEY
            self._base_url = DEEPSEEK_BASE_URL.rstrip("/")
        else:
            self._api_key = QWEN_API_KEY
            self._base_url = _compat_base()
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def _no_think_params(self) -> dict:
        """关闭思考链的参数，按提供商适配：
        - Qwen: enable_thinking=false（老模型忽略）
        - DeepSeek: thinking={type: disabled}（enable_thinking 会被忽略，
          reasoning 仍开启并吃掉 max_tokens，实测 content 为空）
        """
        if self._is_deepseek:
            return {"thinking": {"type": "disabled"}}
        return {"enable_thinking": False}

    def _build_messages(self, prompt: str, system: str = "") -> list[dict]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def generate(self, prompt: str, system: str = "") -> str:
        client = _get_client()
        resp = await client.post(
            f"{self._base_url}/chat/completions",
            headers=self._headers(),
            json={
                "model": self._model,
                "messages": self._build_messages(prompt, system),
                "temperature": self._temperature,
                "max_tokens": self._max_tokens,
                # 关闭思考模式：qwen3.x 默认带思考链，延迟 6-20s → 关闭后 <1s；老模型忽略该参数
                **self._no_think_params(),
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"] or ""

    @staticmethod
    def _parse_tool_message(data: dict) -> dict:
        """解析 OpenAI 兼容响应的 message → {content, tool_calls}。

        function.arguments 为 JSON 串，非法时降级 {}（不抛异常，调用方按无参处理）。
        """
        try:
            message = (data.get("choices") or [{}])[0].get("message") or {}
        except (IndexError, AttributeError):
            return {"content": "", "tool_calls": []}
        calls = []
        for tc in message.get("tool_calls") or []:
            fn = tc.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
                if not isinstance(args, dict):
                    args = {}
            except (json.JSONDecodeError, TypeError):
                args = {}
            calls.append({"id": tc.get("id", ""), "name": fn.get("name", ""), "args": args})
        return {"content": message.get("content") or "", "tool_calls": calls}

    async def generate_with_tools(self, messages: list[dict], tools: list[dict],
                                  system: str = "") -> dict:
        """OpenAI function-calling：tools 透传 + tool_choice=auto。

        返回 {"content": str, "tool_calls": [{"id", "name", "args": dict}]}。
        """
        client = _get_client()
        full_messages = ([{"role": "system", "content": system}] if system else []) + messages
        resp = await client.post(
            f"{self._base_url}/chat/completions",
            headers=self._headers(),
            json={
                "model": self._model,
                "messages": full_messages,
                "tools": tools,
                "tool_choice": "auto",
                "temperature": self._temperature,
                "max_tokens": self._max_tokens,
                **self._no_think_params(),
            },
        )
        resp.raise_for_status()
        return self._parse_tool_message(resp.json())

    async def generate_stream(self, prompt: str, system: str = "") -> AsyncGenerator[str, None]:
        """流式生成 — 每个增量 token 到达即 yield。"""
        client = _get_client()
        async with client.stream(
            "POST",
            f"{self._base_url}/chat/completions",
            headers=self._headers(),
            json={
                "model": self._model,
                "messages": self._build_messages(prompt, system),
                "temperature": self._temperature,
                "max_tokens": self._max_tokens,
                "stream": True,
                # 关闭思考模式（同步接口同理）
                **self._no_think_params(),
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if not data_str or data_str == "[DONE]":
                    continue
                try:
                    chunk = json.loads(data_str)
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    text = (choices[0].get("delta") or {}).get("content") or ""
                    if text:
                        yield text
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass
