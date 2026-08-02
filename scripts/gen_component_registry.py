#!/usr/bin/env python3
"""生成组件注册表清单 docs/COMPONENT_REGISTRY.md（对齐 amap ``scripts/gen_tool_registry.py``）。

扫描各 ``builtin()`` 清单 + ``@component`` 元数据，输出所有已注册组件（召回源 / 记忆
Provider / 上下文 Provider / Agent）的名称、优先级、阶段、来源模块，便于 review 与答辩。

用法（仓库根）：
    PYTHONPATH=backend python scripts/gen_component_registry.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(_ROOT / "backend"))


def _collect() -> list[tuple[str, str, int, str, str]]:
    from app.framework.registry import component_priority

    rows: list[tuple[str, str, int, str, str]] = []

    from app.providers.recall import builtin as recall_builtin

    for s in recall_builtin():
        rows.append(("recall_source", s.name, component_priority(s), getattr(s, "stage", ""), type(s).__module__))

    from app.providers.memory import builtin as memory_builtin

    for p in memory_builtin():
        rows.append(("memory_provider", p.name, component_priority(p), "", type(p).__module__))

    from app.providers.context import builtin as context_builtin

    for p in context_builtin():
        rows.append(("context_provider", p.name, component_priority(p), "", type(p).__module__))

    from app.providers.agents import builtin as agents_builtin

    for name, agent in agents_builtin().items():
        rows.append(("agent", name, component_priority(agent), "", type(agent).__module__))

    return rows


def main() -> int:
    rows = _collect()
    lines = [
        "# 组件注册表（自动生成，请勿手改）",
        "",
        f"> 由 `scripts/gen_component_registry.py` 生成。共 {len(rows)} 个已注册组件。",
        "",
        "| kind | name | priority | stage | module |",
        "|---|---|---|---|---|",
    ]
    for kind, name, prio, stage, mod in sorted(rows):
        lines.append(f"| {kind} | {name} | {prio} | {stage} | `{mod}` |")

    out = _ROOT / "docs" / "COMPONENT_REGISTRY.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(rows)} components)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
