"""BM25 稀疏向量编码器 —— 混合检索的词面召回侧（spec: 混合检索与四bug根治 §1.1）。

为什么需要：纯 dense embedding 只懂"语义邻近"，用户说「面膜」会召回面霜/精华
（护肤语义相邻但品类不同）。BM25 在 token 层做词面精确加权，与 dense 互补
（Anthropic Contextual Retrieval 实证：BM25+embedding 比纯 embedding 显著降低失败率）。

设计要点：
- 中文分词 jieba（``lcut_for_search`` 细粒度，利于短 query 命中长标题）；
  **英文数字型号整体保留**（"JBC-351"/"SK-II"/"MDH-A036" 不可被切碎，型号是电商强信号）；
- BM25 权重 k1=1.2 / b=0.75（业界默认）；语料统计（df / avgdl / N）索引期算好落
  ``data/bm25_stats.json``，查询期只算 tf → 零额外 IO；
- token → 稀疏维度用稳定 hash（32bit，跨进程/重启一致），Qdrant sparse 向量按
  ``indices/values`` 提交；
- 统计缺失时降级为"纯 tf-idf 近似"（idf=1），不抛异常——保证 hybrid 检索永不因
  统计文件缺失而挂掉（降级链原则）。
"""

from __future__ import annotations

import json
import logging
import math
import re
import threading
import zlib
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = [
    "tokenize",
    "encode_document",
    "encode_query",
    "build_corpus_stats",
    "save_stats",
    "load_stats",
    "BM25Stats",
    "STATS_PATH",
]

# BM25 超参（业界默认；k1 控词频饱和、b 控长度归一强度）
_K1 = 1.2
_B = 0.75

STATS_PATH = Path(__file__).resolve().parents[3] / "data" / "bm25_stats.json"

# 型号/英文/数字整体 token（先抽出保护，再对剩余中文分词）
_MODEL_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[-_+][A-Za-z0-9]+)*|\d+(?:\.\d+)?[a-zA-Z]*")

# 电商检索停用词（保留品类词/规格词；只滤纯功能词）
_STOP = {
    "的", "了", "和", "与", "或", "是", "在", "有", "个", "款", "款式", "这", "那",
    "我", "你", "他", "它", "们", "吗", "呢", "吧", "啊", "呀", "哦", "把", "被",
    "请", "帮", "想", "要", "买", "推荐", "一下", "一个", "什么", "怎么", "哪个",
    "可以", "适合", "需要", "还有", "以及", "对于", "关于", "元", "块",
}


class BM25Stats:
    """语料统计：文档频次 df、平均长度 avgdl、文档总数 N。"""

    __slots__ = ("df", "avgdl", "n_docs")

    def __init__(self, df: dict[str, int] | None = None, avgdl: float = 0.0, n_docs: int = 0):
        self.df = df or {}
        self.avgdl = avgdl or 1.0
        self.n_docs = n_docs or 1

    def idf(self, token: str) -> float:
        """BM25 概率型 idf（加 0.5 平滑，下限 0 防负值）。"""
        n_q = self.df.get(token, 0)
        return max(0.0, math.log((self.n_docs - n_q + 0.5) / (n_q + 0.5) + 1.0))

    def to_dict(self) -> dict:
        return {"df": self.df, "avgdl": self.avgdl, "n_docs": self.n_docs}


def tokenize(text: str) -> list[str]:
    """分词：型号/英文/数字整体保留 + 中文 jieba 细分 + 停用词过滤（全部小写）。"""
    if not text:
        return []
    text = text.strip()
    tokens: list[str] = []

    # 1) 抽出型号/英文/数字（整体保留），中文部分留待分词
    last = 0
    chinese_spans: list[str] = []
    for m in _MODEL_RE.finditer(text):
        if m.start() > last:
            chinese_spans.append(text[last : m.start()])
        tokens.append(m.group().lower())
        last = m.end()
    if last < len(text):
        chinese_spans.append(text[last:])

    # 2) 中文段 jieba 细粒度切分
    import jieba

    for span in chinese_spans:
        for t in jieba.lcut_for_search(span):
            t = t.strip().lower()
            if len(t) >= 2 and t not in _STOP and not t.isspace():
                tokens.append(t)
            elif len(t) == 1 and "\u4e00" <= t <= "\u9fff" and t not in _STOP:
                tokens.append(t)  # 单字中文（如"杯""包"）仍是有效品类信号
    return tokens


def _dim(token: str) -> int:
    """token → 稀疏维度（稳定 hash，跨进程一致；zlib.crc32 比内置 hash 稳定）。"""
    return zlib.crc32(token.encode("utf-8")) & 0x7FFFFFFF


def encode_document(text: str, stats: BM25Stats | None = None) -> tuple[list[int], list[float]]:
    """文档侧 BM25 编码 → (indices, values)。

    文档侧用完整 BM25 词频项：``tf * (k1+1) / (tf + k1*(1-b+b*dl/avgdl))``，
    idf 留给查询侧（Qdrant sparse 点积天然完成 idf × tf 的乘法）。
    """
    tokens = tokenize(text)
    if not tokens:
        return [], []
    st = stats or load_stats()
    dl = len(tokens)
    tf: dict[str, int] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    norm = _K1 * (1 - _B + _B * dl / st.avgdl)
    packed: dict[int, float] = {}
    for t, f in tf.items():
        w = f * (_K1 + 1) / (f + norm)
        d = _dim(t)
        packed[d] = max(packed.get(d, 0.0), w)  # hash 冲突取大值
    return list(packed.keys()), list(packed.values())


def encode_query(text: str, stats: BM25Stats | None = None) -> tuple[list[int], list[float]]:
    """查询侧编码 → (indices, values)，值为 idf（与文档侧 tf 项点积即 BM25 分）。"""
    tokens = tokenize(text)
    if not tokens:
        return [], []
    st = stats or load_stats()
    packed: dict[int, float] = {}
    for t in set(tokens):
        w = st.idf(t)
        if w <= 0:
            continue
        d = _dim(t)
        packed[d] = max(packed.get(d, 0.0), w)
    return list(packed.keys()), list(packed.values())


def build_corpus_stats(docs: list[str]) -> BM25Stats:
    """索引期：统计 df / avgdl / N。"""
    df: dict[str, int] = {}
    total_len = 0
    for d in docs:
        toks = tokenize(d)
        total_len += len(toks)
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    n = max(len(docs), 1)
    return BM25Stats(df=df, avgdl=(total_len / n) or 1.0, n_docs=n)


def save_stats(stats: BM25Stats, path: Path | None = None) -> Path:
    p = path or STATS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(stats.to_dict(), ensure_ascii=False), encoding="utf-8")
    return p


_stats_cache: BM25Stats | None = None
_stats_lock = threading.Lock()


def load_stats(path: Path | None = None) -> BM25Stats:
    """进程级缓存加载语料统计；缺失时降级为 idf≈1 的近似（不抛异常）。"""
    global _stats_cache
    if _stats_cache is not None:
        return _stats_cache
    with _stats_lock:
        if _stats_cache is not None:
            return _stats_cache
        p = path or STATS_PATH
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            _stats_cache = BM25Stats(df=raw.get("df", {}), avgdl=raw.get("avgdl", 1.0),
                                     n_docs=raw.get("n_docs", 1))
            logger.info(f"BM25 stats loaded: {_stats_cache.n_docs} docs, "
                        f"{len(_stats_cache.df)} terms, avgdl={_stats_cache.avgdl:.1f}")
        except Exception as e:  # noqa: BLE001 — 统计缺失不阻断混合检索
            logger.warning(f"BM25 stats 缺失({e})，降级近似 idf=1（建议跑 index_product_chunks.py）")
            _stats_cache = BM25Stats(df={}, avgdl=20.0, n_docs=1)
        return _stats_cache


def reset_stats_cache() -> None:
    """测试/重建索引后清缓存。"""
    global _stats_cache
    _stats_cache = None
