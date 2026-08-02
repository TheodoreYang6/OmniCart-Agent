"""ModelProvider 装配 —— 三态选择 Mock / Local / Qwen（进程级缓存）。

优先级：mock_mode > use_local_models > api。
- mock_mode=True                        → MockModelProvider（CI/测试，零重依赖）
- mock_mode=False & USE_LOCAL_MODELS=True → LocalModelProvider（embed/rerank 本地，chat/vision 委托 Qwen）
- 否则                                   → QwenModelProvider（全 API）

gateway 调用点始终传 MOCK_MODE，签名保持不变，向后兼容。
LocalModelProvider 采用懒 import，保证 mock/api 模式无需安装 torch。
"""

from __future__ import annotations

from app.model_gateway.providers.base import ModelProvider
from app.model_gateway.providers.mock_provider import MockModelProvider
from app.model_gateway.providers.qwen_provider import QwenModelProvider

__all__ = ["ModelProvider", "MockModelProvider", "QwenModelProvider", "get_provider"]

_mock: MockModelProvider | None = None
_qwen: QwenModelProvider | None = None
_local: ModelProvider | None = None


def get_provider(mock_mode: bool) -> ModelProvider:
    """返回当前模式对应的 Provider（gateway 传入 MOCK_MODE 作为唯一真相源）。"""
    global _mock, _qwen, _local
    if mock_mode:
        if _mock is None:
            _mock = MockModelProvider()
        return _mock

    from app.core.config import USE_LOCAL_MODELS

    if USE_LOCAL_MODELS:
        if _local is None:
            from app.model_gateway.providers.local_provider import LocalModelProvider

            _local = LocalModelProvider()
        return _local

    if _qwen is None:
        _qwen = QwenModelProvider()
    return _qwen
