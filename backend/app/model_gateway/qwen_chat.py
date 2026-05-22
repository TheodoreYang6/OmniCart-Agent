import httpx
from app.core.config import QWEN_API_KEY, QWEN_BASE_URL


class QwenChat:
    def __init__(self, model: str = "qwen-plus", temperature: float = 0.7, max_tokens: int = 2048):
        self._api_key = QWEN_API_KEY
        self._base_url = QWEN_BASE_URL.rstrip("/")
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def generate(self, prompt: str, system: str = "") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        resp = httpx.post(
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
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["output"]["text"]
