"""内置工具清单 —— 供 ToolRegistry 装配（对齐 ``providers/agents`` 的 builtin 模式）。

返回工具实例列表。延迟导入各工具，避免在包加载期触发重依赖。
"""

from __future__ import annotations

from typing import Any

__all__ = ["builtin", "get_tool_registry"]


def builtin(repo: Any = None) -> list:
    """返回全部内置工具实例。"""
    from app.providers.tools.cart import (
        AddToCartTool,
        ClearCartTool,
        RemoveFromCartTool,
        UpdateCartQtyTool,
        ViewCartTool,
    )
    from app.providers.tools.conversation import (
        ConversationHistoryTool,
        ConversationResetTool,
    )
    from app.providers.tools.order import (
        OrderCancelTool,
        OrderDetailTool,
        OrderListTool,
        OrderPayTool,
        OrderPreviewTool,
        OrderSubmitTool,
        OrderTrackTool,
    )
    from app.providers.tools.preference import (
        PreferenceDeleteTool,
        PreferenceListTool,
        PreferenceSaveTool,
    )
    from app.providers.tools.shopping import (
        CheckInventoryTool,
        CompareProductsTool,
        GetProductDetailTool,
        SearchProductsTool,
    )

    return [
        # 购物车
        ViewCartTool(),
        RemoveFromCartTool(),
        UpdateCartQtyTool(),
        ClearCartTool(),
        AddToCartTool(),
        # 订单下单两阶段：preview 预览 / submit 提交
        OrderPreviewTool(),
        OrderSubmitTool(),
        # 订单闭环（Phase 2b）：list / detail / cancel / track / pay
        OrderListTool(),
        OrderDetailTool(),
        OrderCancelTool(),
        OrderTrackTool(),
        OrderPayTool(),
        # 购物核心（只读）
        SearchProductsTool(),
        GetProductDetailTool(),
        CompareProductsTool(),
        CheckInventoryTool(),
        # 偏好（Phase 6-B3）：save / list / delete
        PreferenceSaveTool(),
        PreferenceListTool(),
        PreferenceDeleteTool(),
        # 会话（Phase 6-B3）：history / reset
        ConversationHistoryTool(),
        ConversationResetTool(),
    ]


_registry = None


def get_tool_registry():
    """进程级单例 ToolRegistry，从 ``builtin()`` 装配。"""
    global _registry
    if _registry is None:
        from app.framework.tools import ToolRegistry

        reg = ToolRegistry(kind="tool")
        reg.register_all(builtin())

        # P2-3 schema_overrides 运营位：文件存在则注入（配了路径但文件缺失 fail-fast，
        # 对齐 amap “配置了但文件不存在 → 启动期 FileNotFoundError” 的约定）
        from app.core.config import TOOL_SCHEMA_OVERRIDES_PATH

        if TOOL_SCHEMA_OVERRIDES_PATH:
            import json
            from pathlib import Path

            reg.set_schema_overrides(json.loads(
                Path(TOOL_SCHEMA_OVERRIDES_PATH).read_text(encoding="utf-8")))

        _registry = reg

        # P0-2 依赖治理：向 framework Planner 注入 LLM 可见工具 schema 来源
        # （framework 不得反向 import providers，改为装配时回调注入）
        from app.framework.orchestration.planner import set_tool_schema_source

        set_tool_schema_source(lambda: _registry.openai_schemas(llm_only=True))
    return _registry
