"""请求级 A2A 黑板 —— Artifact 存储 + asyncio 事件等待 + 订阅回调。

激活 ``schemas/a2a.py`` 的 Artifact 契约（Blackboard architecture /
Anthropic orchestrator-workers 共享上下文模式）：

- 生产者 ``publish`` 主题化产物（topic == artifact_type）；
- 消费者 ``get``（非阻塞）/ ``wait_for``（超时降级 None，不阻塞主链）；
- ``put`` 兼容 ToolRegistry.invoke 的既有 Artifact 落板通路；
- ``spawn`` 托管后台生产者任务（持引用防 GC）。

生命周期 = 单次请求（不序列化、不跨请求共享），挂在
``WorkflowState._blackboard`` 私有属性或 ``ToolContext.blackboard``。

Phase 3 场景：
- 动态编排模式：Router 后台发布 ``memories.ready``，与检索/精排并行，
  Decision 消费前 ``wait_for``；
- supervisor 每步发布 ``<capability>.done``；
- OrderSubmitTool 发布 ``order.created``（经 registry 自动落板）。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextvars import ContextVar

from app.schemas.a2a import Artifact

logger = logging.getLogger(__name__)

__all__ = ["Blackboard", "set_current_board", "current_board", "reset_current_board"]

# 请求级黑板上下文（与 observability.request_context 同模式）。
# LangGraph 节点边界会重建 Pydantic state（动态私有属性丢失），故黑板不能挂 state；
# 在 run_workflow 父任务 set，节点子任务继承可见。
_current_board: ContextVar["Blackboard | None"] = ContextVar("omnicart_blackboard", default=None)


def set_current_board(bb: "Blackboard"):
    """绑定请求级黑板，返回 token 供 reset。"""
    return _current_board.set(bb)


def current_board() -> "Blackboard | None":
    """读当前请求的黑板（未绑定返回 None，消费方按无 A2A 降级）。"""
    return _current_board.get()


def reset_current_board(token) -> None:
    _current_board.reset(token)


class Blackboard:
    """请求级 Artifact 总线（asyncio 单线程语义，无需锁）。"""

    def __init__(self) -> None:
        self._latest: dict[str, Artifact] = {}      # topic -> 最新产物
        self._history: list[Artifact] = []          # 发布顺序全history
        self._events: dict[str, asyncio.Event] = {}
        self._subscribers: dict[str, list] = {}     # topic -> [callback(artifact)]
        self._tasks: list[asyncio.Task] = []        # 后台生产者任务引用

    # ---- 生产 ----

    async def publish(self, topic: str, content: dict | None = None,
                      producer: str = "", confidence: float = 1.0) -> Artifact:
        """发布产物：存储 + 唤醒等待者 + 触发订阅回调。"""
        artifact = Artifact(
            artifact_id=f"A-{uuid.uuid4().hex[:8]}",
            artifact_type=topic,
            producer_agent=producer,
            content=content or {},
            confidence=confidence,
        )
        await self.put(artifact)
        return artifact

    async def put(self, artifact: Artifact) -> None:
        """落板已有 Artifact（ToolRegistry.invoke 兼容入口，topic=artifact_type）。"""
        topic = artifact.artifact_type
        self._latest[topic] = artifact
        self._history.append(artifact)
        self._event(topic).set()
        for cb in self._subscribers.get(topic, []):
            try:
                cb(artifact)
            except Exception as e:  # noqa: BLE001 — 订阅方异常不影响总线
                logger.debug(f"blackboard subscriber error on {topic}: {e}")

    def spawn(self, coro) -> asyncio.Task:
        """托管后台生产者任务（调用方无需自行持引用）。"""
        task = asyncio.create_task(coro)
        self._tasks.append(task)
        return task

    # ---- 消费 ----

    def get(self, topic: str) -> Artifact | None:
        """非阻塞读最新产物。"""
        return self._latest.get(topic)

    async def wait_for(self, topic: str, timeout: float = 2.0) -> Artifact | None:
        """等待产物就绪；超时降级返回 None（消费方按空处理，不阻塞主链）。"""
        if topic in self._latest:
            return self._latest[topic]
        try:
            await asyncio.wait_for(self._event(topic).wait(), timeout)
            return self._latest.get(topic)
        except asyncio.TimeoutError:
            logger.debug(f"blackboard wait_for({topic}) timed out after {timeout}s")
            return None

    def subscribe(self, topic: str, callback) -> None:
        """订阅主题（同步回调，publish 时触发）。"""
        self._subscribers.setdefault(topic, []).append(callback)

    # ---- 观测 ----

    @property
    def history(self) -> list[Artifact]:
        return list(self._history)

    def topics(self) -> list[str]:
        """已发布主题（按首次发布顺序去重）。"""
        seen: list[str] = []
        for a in self._history:
            if a.artifact_type not in seen:
                seen.append(a.artifact_type)
        return seen

    # ---- 内部 ----

    def _event(self, topic: str) -> asyncio.Event:
        if topic not in self._events:
            self._events[topic] = asyncio.Event()
        return self._events[topic]
