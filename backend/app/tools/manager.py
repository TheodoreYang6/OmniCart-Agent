"""V1 MCP-compatible ToolManager — 原子工具统一管理与执行。

每个 Tool 有 Manifest（描述、schema、权限），ToolManager 负责：
- 加载/注册工具
- 校验输入输出
- 权限检查
- 记录 ToolCallRecord
"""

from typing import Any, Optional
from pydantic import BaseModel, Field


class ToolManifest(BaseModel):
    """工具描述清单 — MCP-compatible"""
    tool_name: str
    description: str
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    permission_level: str = "read"     # read / write / admin
    risk_level: str = "low"            # low / medium / high
    allowed_agents: list[str] = Field(default_factory=list)  # 哪些 Agent 可以调用
    timeout_ms: int = 30000
    cacheable: bool = True
    manifest_hash: str = ""


class ToolCallRecord(BaseModel):
    """工具调用记录"""
    call_id: str = ""
    tool_name: str = ""
    agent_name: str = ""
    input_summary: str = ""
    output_summary: str = ""
    latency_ms: int = 0
    status: str = "pending"  # pending / running / success / failed / permission_denied
    error: str = ""


class ToolManager:
    """工具管理器 — V1 内存实现。

    所有 Tool 输出必须是结构化 JSON。
    V1 工具默认只读（permission_level="read"），
    不执行下单、支付、修改账号等写操作。
    """

    def __init__(self):
        self._tools: dict[str, ToolManifest] = {}
        self._handlers: dict[str, callable] = {}  # tool_name → handler function
        self._records: list[ToolCallRecord] = []
        self._register_builtins()

    def _register_builtins(self):
        builtins = [
            ToolManifest(
                tool_name="product_text_search",
                description="使用 Embedding 语义向量检索商品",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}, "category": {"type": "string"}, "top_k": {"type": "integer"}}},
                output_schema={"type": "array", "items": {"type": "object"}},
                permission_level="read", risk_level="low", cacheable=True,
            ),
            ToolManifest(
                tool_name="product_vector_search",
                description="使用 Qdrant 向量相似度检索商品",
                input_schema={"type": "object", "properties": {"query_embedding": {"type": "array"}, "top_k": {"type": "integer"}}},
                output_schema={"type": "array", "items": {"type": "object"}},
                permission_level="read", risk_level="low", cacheable=True,
            ),
            ToolManifest(
                tool_name="review_search",
                description="检索用户评论，支持按 aspect/rating 过滤",
                input_schema={"type": "object", "properties": {"product_id": {"type": "string"}, "aspect": {"type": "string"}}},
                output_schema={"type": "array", "items": {"type": "object"}},
                permission_level="read", risk_level="low", cacheable=True,
            ),
            ToolManifest(
                tool_name="policy_lookup",
                description="查询购物政策、航空规则、售后条款",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
                output_schema={"type": "array", "items": {"type": "object"}},
                permission_level="read", risk_level="low", cacheable=True,
            ),
            ToolManifest(
                tool_name="compatibility_rule_query",
                description="查询设备兼容性规则",
                input_schema={"type": "object", "properties": {"product_id": {"type": "string"}, "user_devices": {"type": "array"}}},
                output_schema={"type": "object"},
                permission_level="read", risk_level="low", cacheable=True,
            ),
            ToolManifest(
                tool_name="structured_filter",
                description="按价格、品类、库存、接口等结构化过滤",
                input_schema={"type": "object", "properties": {"products": {"type": "array"}, "constraints": {"type": "object"}}},
                output_schema={"type": "array", "items": {"type": "object"}},
                permission_level="read", risk_level="low", cacheable=False,
            ),
            ToolManifest(
                tool_name="decision_score_calculator",
                description="计算 7 维加权综合评分",
                input_schema={"type": "object", "properties": {"candidates": {"type": "array"}, "evidence_list": {"type": "array"}, "constraints": {"type": "object"}}},
                output_schema={"type": "object"},
                permission_level="read", risk_level="low", cacheable=False,
            ),
            ToolManifest(
                tool_name="demo_replay_loader",
                description="从 Demo Pack 加载预置中间结果",
                input_schema={"type": "object", "properties": {"scenario_id": {"type": "string"}}},
                output_schema={"type": "object"},
                permission_level="read", risk_level="low", cacheable=True,
            ),
        ]
        for t in builtins:
            self._tools[t.tool_name] = t

    def register(self, manifest: ToolManifest, handler: callable = None):
        self._tools[manifest.tool_name] = manifest
        if handler:
            self._handlers[manifest.tool_name] = handler

    def get_manifest(self, tool_name: str) -> Optional[ToolManifest]:
        return self._tools.get(tool_name)

    def list_all(self) -> list[ToolManifest]:
        return list(self._tools.values())

    def list_by_permission(self, level: str) -> list[ToolManifest]:
        return [t for t in self._tools.values() if t.permission_level == level]

    def can_agent_use(self, tool_name: str, agent_name: str) -> bool:
        manifest = self._tools.get(tool_name)
        if not manifest:
            return False
        if not manifest.allowed_agents:
            return True  # 未限制则所有 Agent 可用
        return agent_name in manifest.allowed_agents

    def execute(self, tool_name: str, inputs: dict, agent_name: str = "") -> dict:
        """执行工具并返回结构化结果 + 记录。"""
        import time
        import uuid

        t0 = time.time()
        call_id = f"TC{uuid.uuid4().hex[:10]}"

        manifest = self._tools.get(tool_name)
        if not manifest:
            record = ToolCallRecord(call_id=call_id, tool_name=tool_name, agent_name=agent_name,
                                     status="failed", error=f"unknown tool: {tool_name}")
            self._records.append(record)
            return {"ok": False, "error": record.error, "record": record.model_dump()}

        if not self.can_agent_use(tool_name, agent_name):
            record = ToolCallRecord(call_id=call_id, tool_name=tool_name, agent_name=agent_name,
                                     status="permission_denied", error=f"agent {agent_name} not allowed")
            self._records.append(record)
            return {"ok": False, "error": record.error, "record": record.model_dump()}

        # V1: 所有工具只读，写操作直接拒绝
        if manifest.permission_level != "read":
            record = ToolCallRecord(call_id=call_id, tool_name=tool_name, agent_name=agent_name,
                                     status="permission_denied",
                                     error="V1 only supports read-only tools. Write/execute tools are disabled.")
            self._records.append(record)
            return {"ok": False, "error": record.error, "record": record.model_dump()}

        handler = self._handlers.get(tool_name)
        latency = int((time.time() - t0) * 1000)

        if handler:
            try:
                result = handler(inputs)
                record = ToolCallRecord(call_id=call_id, tool_name=tool_name, agent_name=agent_name,
                                         input_summary=str(list(inputs.keys())),
                                         output_summary=f"ok ({len(str(result))} chars)",
                                         latency_ms=latency, status="success")
                self._records.append(record)
                return {"ok": True, "data": result, "record": record.model_dump()}
            except Exception as e:
                record = ToolCallRecord(call_id=call_id, tool_name=tool_name, agent_name=agent_name,
                                         latency_ms=latency, status="failed", error=str(e))
                self._records.append(record)
                return {"ok": False, "error": str(e), "record": record.model_dump()}

        # 无 handler 仅做 manifest 校验（mock 模式）
        record = ToolCallRecord(call_id=call_id, tool_name=tool_name, agent_name=agent_name,
                                 input_summary=str(list(inputs.keys())),
                                 output_summary="manifest-only (no handler registered)",
                                 latency_ms=latency, status="success")
        self._records.append(record)
        return {"ok": True, "data": {"manifest": manifest.model_dump(), "inputs": inputs},
                "record": record.model_dump()}

    def get_records(self, limit: int = 20) -> list[ToolCallRecord]:
        return self._records[-limit:]

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def __len__(self):
        return len(self._tools)


# 全局单例
_manager: ToolManager | None = None


def get_tool_manager() -> ToolManager:
    global _manager
    if _manager is None:
        _manager = ToolManager()
    return _manager
