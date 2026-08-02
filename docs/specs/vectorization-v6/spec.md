# 向量化管线 V6 —— 审核定稿清单与施行方案

## 审核结论（对标来源）
- **amap ha3 模式**：schema 集中管理（已借鉴 ✓）；行内容自带完整上下文入向量、结构化 tag 与向量并存过滤（对应本次 Contextual Prefix + payload 补齐）
- **Qwen3-Embedding 官方**：非对称编码——query 侧加 instruct 前缀 / API 侧 text_type=query，文档侧不加。本地 `local_backend.embed_texts(is_query=)` 已实现但从未接线（真 Bug）
- **Anthropic Contextual Retrieval**：chunk 前缀商品上下文，消除跨商品 FAQ/评价混淆命中（本次新增项）
- **Qdrant 实践**：版本化集合蓝绿重建（v4 保留可回滚）；1w 点规模不做 quantization/降维；alias 机制对可重启的演示项目属过度设计，不引入

## 1. 非对称编码接线（P0-1，不需重建索引，立即生效）
- `model_gateway/gateway.py::embed` 增参 `is_query: bool = False`，透传给 provider
- `providers/base.py` embed 协议增参；`local_provider.embed` 传 `lb.embed_texts(texts, is_query=is_query)`；`qwen_provider/qwen_embedding.embed` 在 parameters 加 `"text_type": "query" if is_query else "document"`；`mock_provider` 忽略该参
- 调用侧：`semantic_retriever._embed_query` 与 `hybrid` 查询路径改 `embed([query], "text_embedding", is_query=True)`；索引脚本文档侧保持默认 False
- 查询向量 Redis 缓存 key 加 "q1" 版本盐（避免命中旧的文档模式查询向量）

## 2. build_chunks V6（P0-2，`schemas/product_chunk.py`）
- **Contextual Prefix**：mkt/faq/rev 块 text 统一加前缀 `[{title[:24]}|{brand}] `（summary 本身含全量不加）
- **FAQ 截断 200 → 400**（当前 463/3047 条 15% 被截断，尾部是操作建议与参数）
- **SKU 规格入向量**：summary 块追加 ` | [规格] 容量:30ml/50ml/75ml 颜色:曜石黑/云朵白`（properties 按维度聚合去重，值域截 80 字）
- **rev 块去昵称**：text 改 `评分{rating}/5: {content[:200]}`（昵称保留在 payload 供展示）
- **payload 新增口碑字段**：`avg_rating`、`review_count`、`negative_count`（取自现成 `compute_review_aggregates`，挂在每块 payload）
- `from_qdrant_payload` 同步新字段；本地缓存降级重建函数 `_reconstruct_chunk_text` 同步新文本格式

## 3. 过滤与索引补齐（P0-3，`repositories/qdrant_vector_repo.py`）
- `_build_filter` 增 `brand`（MatchValue/MatchAny，兼容 str 或 list——compare 多路检索可服务端按品牌过滤）与 `rating_min`（avg_rating Range gte）
- `ensure_chunk_collection` / `ensure_payload_indexes` 增 `avg_rating: FLOAT` 索引
- `search_chunks` 透传新过滤键

## 4. 索引脚本 V6（P0-4，`scripts/index_product_chunks.py`）
- **并发 embed**：`asyncio.Semaphore(4)` + `gather` 批间并发；结果按批序号回填保证顺序；本地模型路径 batch 提至 32、无 sleep；API 路径维持 batch 10 + 轻限速
- **失败补位**：单批指数退避重试 3 次（1s/2s/4s），最终失败则抛错终止（绝不跳过错位——index_products.py 的 continue 错位 Bug 引以为戒）
- upsert `wait=False`，收尾一次 `wait=True` + 点数校验（点数 == 块数）
- 集合默认名 bump：`core/config.py` `chunk_collection_name` 默认 `product_chunks_v4_1024 → product_chunks_v6_1024`；旧 v4 集合保留（回滚 = 改回环境变量）

## 5. 产品级旧索引退役（P1，`retrieval/semantic_retriever.py`）
- `_qdrant_search`（products 集合）改为查 chunk 集合 + `chunk_types=["summary","mkt"]`，按 product 聚合 max_score——`_search_impl` 降级语义不变但获得服务端过滤能力
- `_local_search` 降级路径改用 chunk 本地缓存（summary 块过滤），删除对 `product_embeddings.json` 的依赖
- `scripts/index_products.py` 顶部加 DEPRECATED 说明（保留文件供追溯，不再运行）；`qdrant_vector_repo.search_similar/store_embeddings` 标注 deprecated docstring，不删（防外部引用破坏）
- `_qdrant_search`/`search_chunked` 第 7 步的 `get_by_id` N+1：repo 有批量接口则改 `get_by_ids`，没有则保持（PG repo 查一下，有就用）

## 6. 数据小修（随重建）
- SKU 英文 property key 归一（color→颜色 等，仅少量新数据受影响）：`scripts/fix_structural.py` 增 key 映射规则跑一遍；`validate_dataset.py` 补一条 key 必须中文的检查防回归

## 7. 重建与评测（施行顺序）
1. 跑 `scripts/smoke_rag_eval.py` 留存 **v4 基线**报告
2. 实施 §1-§6 代码变更，`py_compile` + 相关单测（test_vector_repo / test_text_retriever / test_retrieval_framework 回归；build_chunks 新断言：前缀/400 截断/规格/无昵称/payload 口碑字段）
3. 全量重建到 `product_chunks_v6_1024`（并发化后预计 ~4 分钟），点数校验
4. 再跑 rag_eval 出 **v6 对比**报告（重点看非对称编码 + Contextual Prefix 的召回/排序收益）；不达预期回滚集合名即可
5. 真实起服冒烟 2 条查询（跨商品 FAQ 混淆场景：如"膳魔师保温杯能保温多久"应命中膳魔师而非任意保温杯）
6. 全量单测 + 集成 + 治理；`docs/工作日志.md` 补工作块 20

## Out of scope
- Qdrant alias / quantization / 降维 / 换 embedding 模型（1w 点规模无收益）
- sparse 混合检索（HybridRetriever 已有文本召回 + RRF，等价物存在）
- 图片向量（将来以 named vectors 加入同集合，本次不动）

## 验收标准
- rag_eval v6 报告核心指标不低于 v4 基线（预期召回/排序提升）
- 全量单测 + 集成 + 治理绿；重建点数 == 生成块数
- 跨商品混淆冒烟 case 命中正确品牌商品