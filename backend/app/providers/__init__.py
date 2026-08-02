"""OmniCart 实现层（providers）—— 各业务 Provider / RecallSource 的具体实现。

对齐 amap-ai-agent 的 ``commons/*_providers``：依赖框架层契约
（``app.framework.*``），通过各子包的 ``builtin()`` 清单被显式装配。framework
绝不反向依赖 providers。
"""

from __future__ import annotations
