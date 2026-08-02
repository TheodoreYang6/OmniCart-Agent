"""OmniCart 框架层（framework）——Protocol 契约 + 编排逻辑，不含业务实现。

分层约定（对齐 amap-ai-agent 的 ``libs/*`` 框架层 + ``commons/*_providers`` 实现层）：

- ``app.framework.*``：框架层。定义 Protocol/ABC 与编排器（RAG / Memory / Context），
  只依赖标准库与本项目基础设施抽象，**不 import 具体业务实现**。
- ``app.providers.*``：实现层。各业务 Provider / RecallSource 的具体实现，
  依赖框架层契约，通过 ``builtin()`` 清单被显式装配。

依赖方向单向：``providers -> framework``，framework 绝不反向依赖 providers。
"""

from __future__ import annotations

__all__ = ["ComponentRegistry", "component"]

from app.framework.registry import ComponentRegistry, component
