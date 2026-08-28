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



def _to_wire_tools(tools: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """内部工具名 -> 线路安全名，并返回反查表。

    内部命名约定是 ``namespace.action``（cart.add / shopping.search），可读性好且与
    ToolRegistry、治理校验、前端契约一致，不该为迁就某个供应商去改。但 DeepSeek 的
    ``/chat/completions`` 要求 ``function.name`` 匹配 ``^[a-zA-Z0-9_-]+$``，带点的名字
    会让整个请求被 400 拒绝（"Invalid 'tools[0].function.name': string does not match
    pattern"），function calling 链路整体不可用。

    点换成双下划线（``cart.add`` -> ``cart__add``）：双下划线在内部命名里不出现，
    反查无歧义；单下划线会与 ``cart.update_qty`` 这类名字混淆。
    """
    mapping: dict[str, str] = {}
    wire: list[dict] = []
    for tool in tools:
        fn = tool.get("function") or {}
        name = fn.get("name", "")
        if "." not in name:
            wire.append(tool)
            continue
        safe = name.replace(".", "__")
        mapping[safe] = name
        wire.append({**tool, "function": {**fn, "name": safe}})
    return wire, mapping


def _to_wire_messages(messages: list[dict], wire_to_internal: dict[str, str]) -> list[dict]:
    """把历史 assistant 消息里的 tool_calls 名字也换成线路名。

    多轮 ReAct 会把上一轮的 ``tool_calls`` 回填进 messages。只转 tools 不转历史消息，
    供应商会因为 ``tool_calls[].function.name`` 不在已声明工具里而报错。
    """
    if not wire_to_internal:
        return messages
    internal_to_wire = {v: k for k, v in wire_to_internal.items()}
    out: list[dict] = []
    for msg in messages:
        calls = msg.get("tool_calls")
        if not calls:
            out.append(msg)
            continue
        new_calls = []
        for call in calls:
            fn = call.get("function") or {}
            name = fn.get("name", "")
            if name in internal_to_wire:
                call = {**call, "function": {**fn, "name": internal_to_wire[name]}}
            new_calls.append(call)
        out.append({**msg, "tool_calls": new_calls})
    return out

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

        工具名在此做线路转换（见 ``_to_wire_tools``）：内部用 ``namespace.action``
        命名，而 DeepSeek 的 ``/chat/completions`` 要求 ``function.name`` 匹配
        ``^[a-zA-Z0-9_-]+$``，带点的名字会让整个请求被 400 拒绝。
        转换只能放在这里 —— 再往上放会改到 mock/local provider，而它们按内部名
        匹配确定性脚本。
        """
        client = _get_client()
        wire_tools, wire_to_internal = _to_wire_tools(tools)
        full_messages = ([{"role": "system", "content": system}] if system else []) + \
            _to_wire_messages(messages, wire_to_internal)
        resp = await client.post(
            f"{self._base_url}/chat/completions",
            headers=self._headers(),
            json={
                "model": self._model,
                "messages": full_messages,
                "tools": wire_tools,
                "tool_choice": "auto",
                "temperature": self._temperature,
                "max_tokens": self._max_tokens,
                **self._no_think_params(),
            },
        )
        resp.raise_for_status()
        parsed = self._parse_tool_message(resp.json())
        # 回程：线路名换回带点的内部名，调用方无感
        for call in parsed.get("tool_calls") or []:
            name = call.get("name", "")
            if name in wire_to_internal:
                call["name"] = wire_to_internal[name]
        return parsed

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
