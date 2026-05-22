"""V1 State Checkpoint — 工作流状态持久化（JSON 文件存储）。

在关键节点后保存 WorkflowState，支持：
- 断点续跑（resume）
- 链路回放（replay）
- Demo Pack 导出（export）
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

from app.schemas.workflow import WorkflowState

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "checkpoints"
CHECKPOINT_NODES = {"router", "visual", "retrieval", "reranker", "evidence_check", "decision", "response", "guard"}


class CheckpointStore:
    """JSON 文件 Checkpoint 存储 — V1 轻量实现。"""

    def __init__(self, directory: Path | None = None):
        self._dir = directory or CHECKPOINT_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, session_id: str, node_name: str, state: WorkflowState):
        if node_name not in CHECKPOINT_NODES:
            return
        file = self._dir / f"{session_id}_{node_name}.json"
        data = {
            "session_id": session_id,
            "node": node_name,
            "timestamp": time.time(),
            "state": state.model_dump(),
        }
        file.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))

    def load(self, session_id: str, node_name: str | None = None) -> Optional[WorkflowState]:
        if node_name:
            file = self._dir / f"{session_id}_{node_name}.json"
            if file.exists():
                data = json.loads(file.read_text())
                return WorkflowState(**data["state"])
            return None

        # 加载最新节点
        files = sorted(self._dir.glob(f"{session_id}_*.json"), reverse=True)
        for f in files:
            data = json.loads(f.read_text())
            return WorkflowState(**data["state"])
        return None

    def list_sessions(self) -> list[str]:
        sessions = set()
        for f in self._dir.glob("*.json"):
            # File pattern: {session_id}_{node}.json
            stem = f.stem
            for node in CHECKPOINT_NODES:
                if stem.endswith(f"_{node}"):
                    sessions.add(stem[:-(len(node) + 1)])
                    break
        return sorted(sessions)

    def delete_session(self, session_id: str):
        for f in self._dir.glob(f"{session_id}_*.json"):
            f.unlink()

    def export_demo_pack(self, session_id: str) -> Optional[dict]:
        """导出完整 Demo Pack（所有节点 checkpoint 合并）。"""
        pack: dict = {"session_id": session_id, "nodes": {}, "final_state": None}
        for f in sorted(self._dir.glob(f"{session_id}_*.json")):
            data = json.loads(f.read_text())
            node = data["node"]
            pack["nodes"][node] = {
                "timestamp": data["timestamp"],
                "trace_steps": data["state"].get("trace_steps", []),
                "evidence_count": len(data["state"].get("evidence_list", [])),
                "product_count": len(data["state"].get("retrieved_products", [])),
                "decision_count": len(data["state"].get("decision_results", [])),
            }
            if node == "guard":
                pack["final_state"] = data["state"]
        return pack if pack["nodes"] else None


# 全局单例
_store = CheckpointStore()


def get_checkpoint_store() -> CheckpointStore:
    return _store
