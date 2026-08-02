"""语义检索器 — Embedding + Qdrant ANN 搜索，替代 jieba 关键词检索。

检索流程:
1. embed(query) → 查询向量
2. Qdrant ANN → top_k * 2 候选
3. 约束过滤 (category, sub_category, price)
4. 返回 top_k

降级策略:
- Qdrant 不可用 → 本地缓存 embedding 做内存余弦相似度暴力搜索 (105 件商品毫秒级)
- Embedding API 不可用 → 抛出异常由上层处理
"""

import json
import logging
import math
import re
from pathlib import Path
from typing import Optional

from app.core.cache import cached, make_key
from app.core.config import REDIS_CACHE_TTL_SEARCH, USE_QDRANT, QDRANT_URL
from app.model_gateway.gateway import get_model_gateway

logger = logging.getLogger(__name__)

_CHUNK_CACHE_FILE = Path(__file__).resolve().parent.parent.parent.parent / "backend" / "data" / "product_chunk_embeddings.json"

# 内存缓存：本地 embedding 文件只加载一次
# （V6：产品级 product_embeddings.json 已退役，降级路径统一走 chunk 缓存）
_local_chunk_cache: dict | None = None
_local_chunk_cache_loaded: bool = False


def _load_local_chunk_cache() -> dict:
    global _local_chunk_cache, _local_chunk_cache_loaded
    if _local_chunk_cache_loaded:
        return _local_chunk_cache or {}
    _local_chunk_cache_loaded = True
    if not _CHUNK_CACHE_FILE.exists():
        logger.warning(f"本地 chunk embedding 缓存不存在: {_CHUNK_CACHE_FILE}，请先运行 scripts/index_product_chunks.py")
        return {}
    try:
        _local_chunk_cache = json.loads(_CHUNK_CACHE_FILE.read_text(encoding="utf-8"))
        logger.info(f"加载本地 chunk embedding 缓存: {_local_chunk_cache.get('count', 0)} 条")
        return _local_chunk_cache
    except Exception as e:
        logger.warning(f"加载本地 chunk embedding 缓存失败: {e}")
        return {}


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """余弦相似度"""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _reconstruct_chunk_text(chunk_type: str, chunk_index: int, product) -> str:
    """从 product.rag_knowledge 重建 chunk 原文（本地缓存降级时使用）。

    本地 product_chunk_embeddings.json 只存向量+元数据不存原文，
    Qdrant 可用时由其返回的 payload.text 提供原文。
    此函数作为降级场景的补齐手段，文本格式与 build_chunks V6 对齐
    （Contextual Prefix / FAQ 截 400 / rev 去昵称）。
    """
    rk = product.rag_knowledge
    if not rk:
        return ""
    prefix = f"[{product.brand} {product.sub_category}] "
    try:
        if chunk_type == "summary":
            desc = (rk.marketing_description or "")[:200]
            return f"{product.title} {product.brand} {product.category} {product.sub_category} {desc}"
        elif chunk_type == "mkt":
            return prefix + (rk.marketing_description or "")[:300]
        elif chunk_type == "faq":
            faqs = rk.official_faq or []
            if chunk_index < len(faqs):
                faq = faqs[chunk_index]
                # faq 不加前缀（与 build_chunks V6 定稿一致）
                return f"Q: {faq.question or ''} A: {(faq.answer or '')[:400]}"
        elif chunk_type == "rev":
            revs = rk.user_reviews or []
            if chunk_index < len(revs):
                rev = revs[chunk_index]
                return f"{prefix}评分{rev.rating or 0}/5: {rev.content or ''}"
    except Exception:
        pass
    return ""


class SemanticRetriever:
    """基于 Embedding 的语义检索器。"""

    def __init__(self, product_repo=None):
        self._repo = product_repo
        self._gateway = get_model_gateway()

    async def _embed_query(self, query: str) -> list[float]:
        """查询向量 + Redis 缓存（多级放宽/多路召回会对同一 query 重复 embed）。

        V6: is_query=True 启用非对称编码；缓存 key 加 q1 版本盐，
        避免命中旧的文档模式查询向量。
        """
        key = make_key("query_emb", "q1", query)

        async def _do() -> list[float]:
            embeddings = await self._gateway.embed([query], "text_embedding", is_query=True)
            return embeddings[0]

        return await cached(key, REDIS_CACHE_TTL_SEARCH, _do)

    @staticmethod
    def _encode_sparse(query: str) -> tuple[list[int], list[float]] | None:
        """BM25 稀疏向量（混合检索词面侧）——仅 ENABLE_HYBRID_RETRIEVAL 开启时生成。

        默认关：评测证伪中文短 query 下 BM25 为净负贡献（purity 0.82→0.78），
        详见 config.enable_hybrid_retrieval 注释与 data/rag_eval_runs/purity-*.json。
        任何异常返回 None → 纯 dense（fail-open）。
        """
        from app.core.config import ENABLE_HYBRID_RETRIEVAL

        if not ENABLE_HYBRID_RETRIEVAL:
            return None
        try:
            from app.retrieval.sparse_encoder import encode_query

            idx, val = encode_query(query)
            return (idx, val) if idx else None
        except Exception as e:  # noqa: BLE001 — 词面侧失败不得阻断检索
            logger.debug(f"sparse encode skipped: {e}")
            return None

    def _resolve_sub_category(self, query: str, sub_category: str | None) -> tuple[str, ...]:
        """子品类硬约束解析（spec §1.4）。

        优先级：QU 给出的 sub_category（经别名归一）> 从 query 推断。
        推断只在 query 含明确品类名词时生效；模糊需求（"补水产品"）返回空，
        走原语义检索路径——宁不过滤也不要错过滤。

        **客服问句不做推断**（实测修正）：“敏感肌长期当化妆水使用是否安全？”这类
        FAQ 里提到的品类词往往不是商品自身品类，硬过滤会把正确商品排除
        （faq hit@5 从 1.0 跌到 0.969）。只在选购意图下用推断硬约束。
        """
        try:
            from app.retrieval.subcategory_alias import infer_from_query, resolve

            if sub_category:
                return resolve(sub_category)
            w = self._chunk_weights(query)
            if w.get("faq", 0) >= 1.0:  # 问句口径 → 不推断品类
                return ()
            known = self._known_sub_categories()
            return infer_from_query(query, known)
        except Exception as e:  # noqa: BLE001 — 归一失败不得阻断检索
            logger.debug(f"sub_category 归一跳过: {e}")
            return ()

    def _known_sub_categories(self) -> set[str]:
        """数据集真实 sub_category 全集（进程级缓存）。"""
        cached_set = getattr(self, "_sub_cat_cache", None)
        if cached_set is not None:
            return cached_set
        names: set[str] = set()
        try:
            if self._repo:
                for p in self._repo.list_all():
                    if getattr(p, "sub_category", ""):
                        names.add(p.sub_category)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"sub_category 全集加载失败: {e}")
        self._sub_cat_cache = names
        return names

    # ---- 同款变体去重（spec §2）----

    _SPEC_NOISE = re.compile(
        r"[0-9]+(\.[0-9]+)?\s*(ml|g|kg|l|mm|cm|寸|码|件|支|片|袋|盒|罐|瓶|套|双|个|升|克)?"
        r"|[A-Za-z][A-Za-z0-9\-]*"
        r"|[黑白红蓝绿粉紫灰金银棕黄]色|颜色|型号|版|款|装|组合|套装|升级"
    )

    @classmethod
    def _variant_key(cls, product) -> tuple:
        """同款判定键：(品牌, 子品类, 归一标题前 12 字)。

        归一 = 去数字/英文型号/规格单位/颜色词，只留中文商品主体词。
        实例："探路者TERRA系列GORE-TEX防水登山鞇42码" 与
              "探路者T6000户外登山鞋GORE-TEX防水透气42码" → 同组
        """
        title = getattr(product, "title", "") or ""
        norm = cls._SPEC_NOISE.sub("", title)
        norm = re.sub(r"[\s　・·\-_/\\|\[\]()（）]", "", norm)[:12]
        return (getattr(product, "brand", "") or "", getattr(product, "sub_category", "") or "", norm)

    def _dedupe_variants(self, ranked: list[tuple[str, float]], top_k: int) -> list[tuple[str, float]]:
        """折叠同款变体：同组只留得分最高一条，余者记入 ``_variant_pids``。

        ranked 已按得分降序（_aggregate_chunks 保证），故首次出现即最优。
        无 repo 时直接截断（降级：不去重优于报错）。
        """
        if not self._repo:
            return ranked[:top_k]
        kept: list[tuple[str, float]] = []
        seen: dict[tuple, str] = {}
        self._variant_map: dict[str, list[str]] = {}
        for pid, score in ranked:
            product = self._repo.get_by_id(pid)
            if product is None:
                continue
            key = self._variant_key(product)
            if key in seen:
                self._variant_map.setdefault(seen[key], []).append(pid)
                continue
            seen[key] = pid
            kept.append((pid, score))
            if len(kept) >= top_k:
                break
        return kept

    async def search(
        self,
        query: str,
        top_k: int = 10,
        category: str | None = None,
        sub_category: str | None = None,
        price_max: float | None = None,
        price_min: float | None = None,
    ) -> list[dict]:
        """语义检索 + Redis 缓存。"""
        cache_key = make_key("semantic_search", query, category or "", sub_category or "",
                             str(price_max or ""), str(price_min or ""), str(top_k))

        async def _do_search() -> list[dict]:
            return await self._search_impl(query, top_k, category, sub_category, price_max, price_min)

        return await cached(cache_key, REDIS_CACHE_TTL_SEARCH, _do_search)

    async def _search_impl(
        self,
        query: str,
        top_k: int,
        category: str | None,
        sub_category: str | None,
        price_max: float | None,
        price_min: float | None,
    ) -> list[dict]:
        # 1. Embed query（带缓存）
        try:
            query_vec = await self._embed_query(query)
        except Exception as e:
            logger.error(f"Embedding API 调用失败: {e}")
            return await self._fallback_text_search(query, top_k, category, sub_category, price_max, price_min)

        # 2. 向量搜索
        candidates = await self._vector_search(query_vec, top_k * 3)

        # 3. 向量搜索无结果 → 回退文本搜索
        if not candidates:
            logger.info("向量搜索无结果，回退文本搜索")
            return await self._fallback_text_search(query, top_k, category, sub_category, price_max, price_min)

        # 4. 约束过滤
        candidates = self._apply_filters(candidates, category, sub_category, price_max, price_min)

        # 5. 返回 top_k
        return candidates[:top_k]

    async def _vector_search(self, query_vec: list[float], top_k: int) -> list[dict]:
        """Qdrant ANN → 降级本地余弦相似度"""
        if USE_QDRANT and QDRANT_URL:
            try:
                return self._qdrant_search(query_vec, top_k)
            except Exception as e:
                logger.warning(f"Qdrant 搜索失败，降级本地: {e}")

        return self._local_search(query_vec, top_k)

    def _qdrant_search(self, query_vec: list[float], top_k: int) -> list[dict]:
        """产品级降级检索（V6：旧 products 集合已退役，改查 chunk 集合的
        summary/mkt 块按商品聚合 max_score——语义等价且获得服务端过滤能力）。"""
        from app.repositories.vector_repo import get_vector_repo

        hits_raw = get_vector_repo().search_chunks(
            query_vec, top_k * 3, chunk_types=["summary", "mkt"])
        best: dict[str, float] = {}
        for h in hits_raw:
            pid = h["product_id"]
            if h["score"] > best.get(pid, -1.0):
                best[pid] = h["score"]

        hits = []
        for pid, score in sorted(best.items(), key=lambda x: -x[1])[:top_k]:
            product = self._repo.get_by_id(pid) if self._repo else None
            if product is None:
                continue
            hits.append(self._product_to_result(product, score))
        return hits

    def _local_search(self, query_vec: list[float], top_k: int) -> list[dict]:
        """本地降级检索（V6：改用 chunk 本地缓存的 summary/mkt 块聚合，
        不再依赖已退役的 product_embeddings.json）。"""
        chunk_hits = self._local_chunk_search(query_vec, top_k * 4)
        best: dict[str, float] = {}
        for h in chunk_hits:
            if h.get("chunk_type") not in ("summary", "mkt"):
                continue
            pid = h["product_id"]
            if h["score"] > best.get(pid, -1.0):
                best[pid] = h["score"]

        hits = []
        for pid, score in sorted(best.items(), key=lambda x: -x[1])[:top_k]:
            product = self._repo.get_by_id(pid) if self._repo else None
            if product is None:
                continue
            hits.append(self._product_to_result(product, score))
        return hits

    def _apply_filters(
        self,
        candidates: list[dict],
        category: str | None,
        sub_category: str | None,
        price_max: float | None,
        price_min: float | None,
    ) -> list[dict]:
        filtered = []
        for item in candidates:
            if category and item.get("category") != category:
                continue
            if sub_category and item.get("sub_category") != sub_category:
                continue
            price = item.get("price", 0)
            if price_max is not None and price > price_max:
                continue
            if price_min is not None and price < price_min:
                continue
            filtered.append(item)
        return filtered

    async def _fallback_text_search(
        self,
        query: str,
        top_k: int,
        category: str | None,
        sub_category: str | None,
        price_max: float | None,
        price_min: float | None,
    ) -> list[dict]:
        """Embedding API 挂了时的最后兜底：简单的子串匹配"""
        if not self._repo:
            return []

        try:
            candidates = self._repo.filter_by(category, sub_category, None, price_max, price_min)
        except Exception:
            candidates = self._repo.list_all() if hasattr(self._repo, 'list_all') else []

        if not candidates:
            return []

        query_lower = query.lower()
        scored = []
        for p in candidates:
            score = 0.0
            text = (p.title + " " + p.brand + " " + p.category + " " + p.sub_category).lower()
            for kw in query_lower.split():
                if len(kw) >= 2 and kw in text:
                    score += 1.0
            if score > 0:
                scored.append((p, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [self._product_to_result(p, s) for p, s in scored[:top_k]]

    # ---- Chunked Search ----

    async def search_chunked(
        self,
        query: str,
        top_k: int = 10,
        category: str | None = None,
        sub_category: str | None = None,
        price_max: float | None = None,
        price_min: float | None = None,
        aggregation: str = "max_score",
        rating_min: float | None = None,
        chunk_focus: str | None = None,
    ) -> list[dict]:
        """块级语义检索 → 聚合到产品级别。

        rating_min: 口碑下限（avg_rating 服务端 Range 过滤）；
        chunk_focus: 只检索指定块类型（rev/faq，原子检索，spec omni-harness D3）。
        """
        from app.core.config import CHUNK_COLLECTION_NAME as _coll

        # 缓存 key 含集合名：切换 v4/v6 集合时不串用旧集合的结果缓存
        cache_key = make_key("chunk_search", _coll, query, str(top_k), category or "", sub_category or "",
                             str(price_max or ""), str(price_min or ""), aggregation,
                             str(rating_min or ""), chunk_focus or "")

        async def _do() -> list[dict]:
            return await self._chunk_search_impl(
                query, top_k, category, sub_category, price_max, price_min, aggregation,
                rating_min=rating_min, chunk_focus=chunk_focus,
            )

        return await cached(cache_key, REDIS_CACHE_TTL_SEARCH, _do)

    async def _chunk_search_impl(
        self,
        query: str,
        top_k: int,
        category: str | None,
        sub_category: str | None,
        price_max: float | None,
        price_min: float | None,
        aggregation: str,
        rating_min: float | None = None,
        chunk_focus: str | None = None,
    ) -> list[dict]:
        # 1. Embed query（带缓存）
        try:
            query_vec = await self._embed_query(query)
        except Exception as e:
            logger.error(f"Chunk search: Embedding API 调用失败: {e}")
            return await self._fallback_text_search(query, top_k, category, sub_category, price_max, price_min)

        # 2. 块级向量搜索 (检索 top_k * 10 个块, 服务端 payload 过滤)
        # 子品类硬约束（spec §1.4）：口语词归一为数据集真实值（洗面奶→洁面），
        # query 含明确品类名词时先做精确过滤检索——避开语义漂移（面膜→面霜/精华）
        sub_values = self._resolve_sub_category(query, sub_category)
        filters = {"category": category, "sub_category": sub_values or sub_category,
                   "price_max": price_max, "price_min": price_min,
                   "rating_min": rating_min}
        chunk_types = [chunk_focus] if chunk_focus else None
        # 混合检索：BM25 稀疏向量（词面侧）与 dense 一同下推，服务端 RRF 融合
        # —— 纯语义会把"敏感肌补水产品"漂到口红（实测），词面侧把品类词权重顶住
        sparse = self._encode_sparse(query)
        chunk_hits = await self._chunk_vector_search(query_vec, top_k * 10, filters, chunk_types,
                                                     sparse=sparse)

        # 2b. 子品类硬约束命中数不足 → 放宽到 category（spec §1.4：≥阀值直接用）。
        # 避免小库存品类（如洁面仅 1 款）因硬过滤而只能返回孤例；已命中的精确结果
        # 置顶保留，不足部分用放宽检索补齐（不是丢弃硬约束，而是先精确后相关）。
        if sub_values and not (rating_min is not None or chunk_focus is not None):
            _exact_pids = {h.get("product_id") for h in chunk_hits if h.get("product_id")}
            if len(_exact_pids) < min(3, top_k):
                _relaxed_filters = dict(filters, sub_category=None)
                _relaxed = await self._chunk_vector_search(query_vec, top_k * 10, _relaxed_filters,
                                                           chunk_types, sparse=sparse)
                if _relaxed:
                    logger.info(f"子品类 {sub_values} 仅 {len(_exact_pids)} 款，"
                                f"放宽至 category 补齐（精确结果置顶）")
                    _seen = {(h.get("chunk_id"), h.get("product_id")) for h in chunk_hits}
                    chunk_hits = chunk_hits + [h for h in _relaxed
                                               if (h.get("chunk_id"), h.get("product_id")) not in _seen]
                    sub_values = ()  # 已放宽：后置 payload 过滤不再按子品类卡

        # 显式硬过滤（口碑下限/块聚焦）存在时，降级/补齐路径必须禁用——
        # 产品级搜索不支持这些过滤，降级会把不满足约束的商品静默塞回（bug 实证：
        # rating_min=4.5 全库无匹配时降级返回了 3.8 分商品）。宁返空让上层诚实告知。
        _hard_filtered = rating_min is not None or chunk_focus is not None

        # 3. 块级搜索无结果 → 降级旧产品级搜索（硬过滤场景不降级）
        if not chunk_hits:
            if _hard_filtered:
                logger.info("Chunk search 硬过滤后无结果，不降级（保持约束语义）")
                return []
            logger.info("Chunk search 无结果，降级产品级搜索")
            return await self._search_impl(query, top_k, category, sub_category, price_max, price_min)

        # 4. 约束过滤 (基于块的 payload)
        chunk_hits = self._apply_chunk_filters(chunk_hits, category, sub_values or sub_category,
                                               price_max, price_min)

        # 4b. 约束过滤后无结果 → 降级产品级搜索（硬过滤场景不降级）
        if not chunk_hits:
            if _hard_filtered:
                return []
            logger.info("Chunk 约束过滤后无结果，降级产品级搜索")
            return await self._search_impl(query, top_k, category, sub_category, price_max, price_min)

        # 5. 按 product_id 分组
        chunk_groups: dict[str, list[dict]] = {}
        for ch in chunk_hits:
            pid = ch["product_id"]
            if pid not in chunk_groups:
                chunk_groups[pid] = []
            chunk_groups[pid].append(ch)

        # 6. 聚合到产品级别 + 同款变体去重（spec §2）
        #    数据集存 81 组归一标题近重复（同款不同 product_id），按 pid 去重无感
        #    → 用户看到"同一产品的不同页面"。先多取候选再折叠，保证去重后仍有 top_k 款
        ranked_all = self._aggregate_chunks(chunk_groups, aggregation, query=query)
        ranked_pids = self._dedupe_variants(ranked_all, top_k)

        # 7. 构建产品结果（复用 _product_to_result）
        results = []
        for pid, agg_score in ranked_pids:
            product = self._repo.get_by_id(pid) if self._repo else None
            if product is None:
                continue
            result = self._product_to_result(product, agg_score)
            # 附加匹配的块信息（含 payload 正文，供 evidence 内容提取）
            matched_chunks = chunk_groups.get(pid, [])
            result["matched_chunks"] = []
            for c in matched_chunks[:5]:
                payload = c.get("payload", {})
                chunk_text = payload.get("text", "")
                # 本地缓存降级时payload无text字段 → 从product.rag_knowledge重建
                if not chunk_text and product.rag_knowledge:
                    chunk_text = _reconstruct_chunk_text(
                        c["chunk_type"],
                        payload.get("chunk_index", 0),
                        product,
                    )
                result["matched_chunks"].append({
                    "chunk_type": c["chunk_type"],
                    "chunk_id": c["chunk_id"],
                    "score": c["score"],
                    "payload": {
                        "text": chunk_text,
                        "faq_question": payload.get("faq_question", ""),
                        "title": payload.get("title", ""),
                        "brand": payload.get("brand", ""),
                    },
                })
            result["matched_chunk_count"] = len(matched_chunks)
            # 同款变体数（折叠掉的重复条目，供前端展示"另有 N 个相似款"）
            _variants = getattr(self, "_variant_map", {}).get(pid) or []
            if _variants:
                result["variant_count"] = len(_variants)
                result["variant_product_ids"] = _variants[:5]
            results.append(result)

        # 8. 如果聚合后结果不足 top_k，用产品级搜索补齐（硬过滤场景不补：补齐会混入不满足约束的商品）
        if len(results) < top_k and not _hard_filtered:
            fallback = await self._search_impl(query, top_k, category, sub_category, price_max, price_min)
            existing_ids = {r["product_id"] for r in results}
            for fb in fallback:
                if fb["product_id"] not in existing_ids:
                    fb.setdefault("matched_chunks", [])
                    fb.setdefault("matched_chunk_count", 0)
                    results.append(fb)
                    existing_ids.add(fb["product_id"])
                    if len(results) >= top_k:
                        break

        return results[:top_k]

    async def _chunk_vector_search(
        self, query_vec: list[float], top_k: int, filters: dict | None = None,
        chunk_types: list[str] | None = None,
        sparse: tuple[list[int], list[float]] | None = None,
    ) -> list[dict]:
        """统一 chunk 集合 ANN（服务端 payload 过滤，可选 dense+BM25 混合）→ 降级本地块缓存。"""
        if USE_QDRANT and QDRANT_URL:
            try:
                from app.repositories.vector_repo import get_vector_repo
                hits = get_vector_repo().search_chunks(query_vec, top_k, filters=filters,
                                                       chunk_types=chunk_types, sparse=sparse)
                if hits:
                    return hits
            except Exception as e:
                logger.warning(f"Qdrant chunk 搜索失败，降级本地: {e}")

        return self._local_chunk_search(query_vec, top_k)

    def _local_chunk_search(self, query_vec: list[float], top_k: int) -> list[dict]:
        """本地块级余弦相似度暴力搜索。"""
        cache = _load_local_chunk_cache()
        chunks_data = cache.get("chunks", [])
        if not chunks_data:
            return []

        scored = []
        for item in chunks_data:
            emb = item.get("embedding")
            if not emb or len(emb) != len(query_vec):
                continue
            sim = _cosine_similarity(query_vec, emb)
            if sim > 0.0:
                payload = item.get("payload", {})
                scored.append({
                    "product_id": payload.get("product_id", ""),
                    "chunk_id": item.get("chunk_id", ""),
                    "chunk_type": item.get("chunk_type", ""),
                    "category": payload.get("category", ""),
                    "sub_category": payload.get("sub_category", ""),
                    "price": payload.get("price", 0),
                    "score": sim,
                    "payload": payload,
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def _apply_chunk_filters(
        self,
        chunks: list[dict],
        category: str | None,
        sub_category: str | tuple | list | None,
        price_max: float | None,
        price_min: float | None,
    ) -> list[dict]:
        # sub_category 可为单值或归一后的值集合（别名一对多）
        sub_set = (set(sub_category) if isinstance(sub_category, (tuple, list, set))
                   else ({sub_category} if sub_category else set()))
        filtered = []
        for ch in chunks:
            if category and ch.get("category") != category:
                continue
            if sub_set and ch.get("sub_category") not in sub_set:
                continue
            price = ch.get("price", 0)
            if price_max is not None and price > price_max:
                continue
            if price_min is not None and price < price_min:
                continue
            filtered.append(ch)
        return filtered

    # 问句标记：命中则 faq 块是正确信号（用户在问商品能不能用/怎么用）
    _QUESTION_MARKS = (
        "？", "?", "能否", "是否", "可否", "会不会", "能不能", "可不可以", "能用吗",
        "如何", "怎么用", "怎么洗", "需注意", "需要注意", "注意什么", "多久", "几天",
        "有效吗", "安全吗", "活性", "成分", "保质期", "保修", "退换", "兼容", "参数",
    )
    # 选购句标记（优先于问句标记："面膜哪个好？"是选购而非客服问题）
    _SHOPPING_MARKS = ("推荐", "哪个好", "哪款", "有没有", "想买", "求推", "性价比",
                       "预算", "以内", "好物", "适合什么", "类型的产品", "同类")

    @classmethod
    def _chunk_weights(cls, query: str | None) -> dict[str, float]:
        """按 query 类型选块权重（spec §1.4 实测调优）。

        选购句（默认）：faq/rev 降权 —— 保品类纯度，防止"敏感肌补水"漂到粉底液
        （FAQ 里写了"敏感肌能用吗"的商品遍地）。
        客服问句：faq 回高位 —— 用户就是在问商品 FAQ，压低反而错。
        """
        q = (query or "").strip()
        shopping = any(m in q for m in cls._SHOPPING_MARKS)
        question = (not shopping) and any(m in q for m in cls._QUESTION_MARKS) and len(q) >= 6
        if question:
            return {"summary": 1.0, "mkt": 0.95, "faq": 1.0, "rev": 0.8}
        return {"summary": 1.0, "mkt": 0.95, "faq": 0.72, "rev": 0.6}

    def _aggregate_chunks(
        self,
        chunk_groups: dict[str, list[dict]],
        aggregation: str = "max_score",
        query: str | None = None,
    ) -> list[tuple[str, float]]:
        """将块级得分聚合为产品级得分。

        块权重（串味 bug 根治，spec §1.4实测修正）：
        summary/mkt 代表"商品是什么"，是品类归属的权威信号；
        faq/rev 代表"能不能用/好不好用"，跳品类重度高——实测坐实：
        query"适合敏感肌的补水产品" top8 全是 faq 块，命中粉底液/洗手液/身体乳
        （它们的 FAQ 里都写着"敏感肌能用吗"）；只搜 summary+mkt 则立刻纯净。
        **且 max_score 也必须加权**（旧实现下 max_score 完全绕过权重表）。

        但权重不能一刀切：用户直接问问题（"敏感肌能用吗？"）时 faq 块本就是正确信号，
        压低会伤 faq hit@1（实测 0.969→0.922）。故按 query 类型取权重：
        问句 → faq 高位；选购句 → faq/rev 降权保品类纯度。
        """
        _WEIGHTS = self._chunk_weights(query)

        product_scores = []
        for pid, chunks in chunk_groups.items():
            if aggregation == "max_score":
                # 加权 max：品类权威块（summary/mkt）优先，faq/rev 需明显更相关才能胜出
                score = max(c["score"] * _WEIGHTS.get(c.get("chunk_type", ""), 0.7)
                            for c in chunks)
            elif aggregation == "weighted":
                weighted_sum = 0.0
                weight_total = 0.0
                for c in chunks:
                    w = _WEIGHTS.get(c.get("chunk_type", ""), 0.5)
                    if c["score"] > 0.4:
                        weighted_sum += c["score"] * w
                        weight_total += w
                score = weighted_sum / max(weight_total, 0.001) if weight_total > 0 else 0.0
            else:
                score = max(c["score"] * _WEIGHTS.get(c.get("chunk_type", ""), 0.7)
                            for c in chunks)  # fallback: 同加权 max

            product_scores.append((pid, round(score, 4)))

        product_scores.sort(key=lambda x: x[1], reverse=True)
        return product_scores

    def _product_to_result(self, product, score: float = 0.0) -> dict:
        evidence_ids = [f"E-MKT-{product.product_id}-0"]
        if product.rag_knowledge:
            for i in range(len(product.rag_knowledge.official_faq)):
                evidence_ids.append(f"POL-{product.product_id}-{i}")
            for i in range(len(product.rag_knowledge.user_reviews)):
                evidence_ids.append(f"R-{product.product_id}-{i}")

        return {
            "product_id": product.product_id,
            "title": product.title,
            "brand": product.brand,
            "category": product.category,
            "sub_category": product.sub_category,
            "price": product.base_price,
            "image_urls": [self._repo.resolve_image_url(product.product_id)] if self._repo and hasattr(self._repo, 'resolve_image_url') else [],
            "skus": [s.model_dump() for s in product.skus],
            "rag_knowledge": product.rag_knowledge.model_dump() if product.rag_knowledge else None,
            "description": product.rag_knowledge.marketing_description if product.rag_knowledge else "",
            "score": round(score, 4),
            "evidence_ids": evidence_ids,
        }
