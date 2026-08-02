"""共享 pytest fixtures — 测试始终使用 JSON + Stub 后端。"""

import os

# 强制测试模式：清空数据库连接串，确保测试使用 JSON + Stub 后端
# 必须在任何 app 导入之前设置
os.environ["DATABASE_URL"] = ""
os.environ["QDRANT_URL"] = ""
os.environ["REDIS_URL"] = ""
os.environ["OMNICART_MOCK_MODE"] = "true"

import pytest

# 测试侧 composition root：触发 graph 的 capability 注册副作用（P0-1 能力表下沉后，
# providers 层不再 import workflow；直调工具的测试需由此处保证能力已就位）
import app.workflow.graph  # noqa: F401, E402

# 预装配工具注册表（P0-2：同时向 framework Planner 注入工具 schema 来源，
# 与生产 startup 预装配对称；否则直调 LLMPlanner 的测试拿到空工具表）
from app.providers.tools import get_tool_registry  # noqa: E402

get_tool_registry()

from app.repositories.json_product_repo import JsonProductRepository
from app.repositories.stub_vector_repo import StubVectorRepository
from app.retrieval.text_retriever import TextRetriever
from app.decision.scoring import DecisionScoring


@pytest.fixture(scope="module")
def json_product_repo():
    """从真实数据集加载的 JSON 产品仓库。"""
    return JsonProductRepository()


@pytest.fixture(scope="module")
def text_retriever(json_product_repo):
    """使用 JSON 仓库的 TextRetriever。"""
    return TextRetriever(json_product_repo)


@pytest.fixture(scope="module")
def stub_vector_repo():
    """Stub 向量仓库 — 始终返回空结果。"""
    return StubVectorRepository()


@pytest.fixture(scope="module")
def decision_scoring():
    """决策评分器。"""
    return DecisionScoring()


# ---- 框架层共享 fixtures（spec §八）----


@pytest.fixture
def fake_recall_source():
    """工厂：构造可配置的 fake RecallSource（无外部依赖）。"""
    from app.framework.retrieval import STAGE_RECALL, RecallSource, RetrievalResult

    def _make(name="fake", *, products=None, evidence=None, stage=STAGE_RECALL,
              is_required=False, priority=100):
        class _FakeSource(RecallSource):
            async def search(self, query):
                return RetrievalResult(name, products=list(products or []), evidence=list(evidence or []))

        src = _FakeSource()
        src.name, src.stage, src.is_required, src.priority = name, stage, is_required, priority
        return src

    return _make


@pytest.fixture
def fake_memory_provider():
    """工厂：构造可配置的 fake MemoryProvider。"""
    from app.framework.memory import MemoryProvider, MemoryRecallResult

    def _make(name="fake", *, items=None):
        class _FakeProvider(MemoryProvider):
            async def recall(self, request):
                return MemoryRecallResult(name, items=list(items or []))

        p = _FakeProvider()
        p.name = name
        return p

    return _make


@pytest.fixture
def mock_gateway():
    """Mock ModelGateway — chat/embed/rerank/chat_stream 返回确定性制品。"""

    class _MockGateway:
        async def chat(self, capability, prompt, system=""):
            return "mock-answer"

        async def chat_stream(self, capability, prompt, system=""):
            for ch in "mock":
                yield ch

        async def embed(self, texts, capability="text_embedding"):
            return [[0.1, 0.2, 0.3] for _ in texts]

        async def rerank(self, query, documents, capability="text_reranking", top_n=10):
            return [
                {"index": i, "document": d, "relevance_score": 1.0 - i * 0.05}
                for i, d in enumerate(documents[: top_n or 10])
            ]

    return _MockGateway()
