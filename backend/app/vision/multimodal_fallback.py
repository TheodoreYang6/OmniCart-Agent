"""V1 Tiered Multimodal Fallback — 多模态分层降级链路。

Fallback 层级:
  Level 0: 真实 Qwen-VL 视觉解析
  Level 1: Mock 视觉解析（预置结果）
  Level 2: 纯文本模式（忽略图片，仅用文字 query）
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class MultimodalFallback:
    """多模态降级管理器。"""

    def __init__(self):
        self._level = 0

    @property
    def current_level(self) -> int:
        return self._level

    @property
    def level_description(self) -> str:
        return {
            0: "Qwen-VL real inference",
            1: "Mock visual parse (fallback)",
            2: "Text-only mode (image ignored)",
        }.get(self._level, "unknown")

    def try_visual_parse(self, image_url: str, user_query: str) -> tuple[Optional[dict], dict]:
        """尝试三级降级的视觉解析。"""
        status = {"level": self._level, "description": self.level_description, "attempts": []}

        # Level 0: 真实 Qwen-VL
        self._level = 0
        try:
            from app.model_gateway.gateway import get_model_gateway
            gateway = get_model_gateway()
            result = gateway.vision(image_url, user_query)
            if result and result.get("product_name"):
                status["attempts"].append("level_0_success")
                return result, status
            status["attempts"].append("level_0_no_result")
        except Exception as e:
            logger.warning(f"Level 0 visual parse failed: {e}")
            status["attempts"].append(f"level_0_error: {e}")

        # Level 1: Mock 降级
        self._level = 1
        try:
            from app.model_gateway.mock_model import mock_vision_parse
            result = mock_vision_parse(image_url)
            if result:
                status["attempts"].append("level_1_success")
                return result, status
            status["attempts"].append("level_1_no_result")
        except Exception as e:
            logger.warning(f"Level 1 mock fallback failed: {e}")
            status["attempts"].append(f"level_1_error: {e}")

        # Level 2: 纯文本
        self._level = 2
        status["attempts"].append("level_2_text_only")
        return None, status

    def reset(self):
        self._level = 0
