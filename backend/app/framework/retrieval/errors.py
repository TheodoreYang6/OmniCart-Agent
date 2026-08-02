"""RAG 框架层异常。"""

from __future__ import annotations


class RetrievalError(Exception):
    """检索框架基类异常。"""


class RequiredSourceError(RetrievalError):
    """必需召回源失败（失败/超时），导致整体检索上抛。"""

    def __init__(self, source_name: str, cause: object) -> None:
        self.source_name = source_name
        self.cause = cause
        super().__init__(f"required recall source {source_name!r} failed: {cause}")
