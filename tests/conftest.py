"""共享 pytest fixtures — 测试始终使用 JSON + Stub 后端。"""

import os

# 强制测试模式：清空数据库连接串，确保测试使用 JSON + Stub 后端
# 必须在任何 app 导入之前设置
os.environ["DATABASE_URL"] = ""
os.environ["QDRANT_URL"] = ""
os.environ["REDIS_URL"] = ""
os.environ["OMNICART_MOCK_MODE"] = "true"

import pytest

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
