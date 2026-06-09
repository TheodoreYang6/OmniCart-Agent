"""Qwen-VL 视觉理解 — 多模态生成 API"""
import base64
from pathlib import Path

import httpx
from app.core.config import QWEN_API_KEY, QWEN_BASE_URL

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
    return _client


class QwenVision:
    def __init__(self, model: str = "qwen-vl-plus", temperature: float = 0.3, max_tokens: int = 2048):
        self._api_key = QWEN_API_KEY
        self._base_url = QWEN_BASE_URL.rstrip("/")
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def analyze(self, image_path: str, prompt: str, system: str = "") -> str:
        """解析单张图片"""
        image_data = self._encode_image(image_path)

        messages = []
        if system:
            messages.append({"role": "system", "content": [{"text": system}]})
        messages.append({
            "role": "user",
            "content": [
                {"image": image_data},
                {"text": prompt},
            ],
        })

        return await self._call_api(messages)

    async def analyze_bytes(self, image_bytes: bytes, content_type: str, prompt: str, system: str = "") -> str:
        """解析内存中的图片数据"""
        image_data = f"data:{content_type};base64,{base64.b64encode(image_bytes).decode()}"

        messages = []
        if system:
            messages.append({"role": "system", "content": [{"text": system}]})
        messages.append({
            "role": "user",
            "content": [
                {"image": image_data},
                {"text": prompt},
            ],
        })

        return await self._call_api(messages)

    async def _call_api(self, messages: list[dict]) -> str:
        client = _get_client()
        resp = await client.post(
            f"{self._base_url}/services/aigc/multimodal-generation/generation",
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
        msg = data["output"]["choices"][0]["message"]
        content = msg["content"]
        if isinstance(content, list):
            return "".join(p.get("text", "") for p in content if "text" in p)
        return str(content)

    @staticmethod
    def _encode_image(path: str) -> str:
        p = Path(path)
        suffix = p.suffix.lower()
        mime = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp", ".gif": "image/gif",
        }.get(suffix, "image/png")
        data = base64.b64encode(p.read_bytes()).decode()
        return f"data:{mime};base64,{data}"
