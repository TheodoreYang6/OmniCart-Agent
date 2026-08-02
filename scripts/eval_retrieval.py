"""检索层命中评测 — v4/v6 向量化方案对比（hit@1 / hit@5 / MRR@10）。

构造方式：均匀抽样商品，每件商品出 2 类查询——
  faq   : 该商品第 1 条 FAQ 的 question 原文（真实用户问法；跨商品混淆的重灾区，
          直接度量 Contextual Prefix 收益）
  title : 品牌 + 子品类（导购主流查询形态）
期望：top-k 内命中该 product_id。

直接调 SemanticRetriever._chunk_search_impl（绕过 Redis 缓存，保证 v4/v6 对比公平）。
集合名由 OMNICART_CHUNK_COLLECTION 环境变量控制。

--with-rerank：额外输出「召回后 vs 精排后」对比口径（与主链一致：
头部 8 候选过 RerankFusion，尾部保留召回序），量化 reranker 对排序的真实增益。

用法:
    PYTHONPATH=backend python scripts/eval_retrieval.py --tag v4_baseline
    OMNICART_CHUNK_COLLECTION=product_chunks_v6_1024 PYTHONPATH=backend \
        python scripts/eval_retrieval.py --tag v6
    PYTHONPATH=backend python scripts/eval_retrieval.py --tag v6_rr --with-rerank
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

try:
    import nest_asyncio

    nest_asyncio.apply()
except ImportError:
    pass

SAMPLE_PER_CATEGORY = 8  # 8 品类 × 8 商品 × 2 查询 = 128 条
TOP_K = 10


def build_cases() -> list[dict]:
    from app.repositories.json_product_repo import JsonProductRepository

    repo = JsonProductRepository()
    by_cat: dict[str, list] = {}
    for p in repo.list_all():
        by_cat.setdefault(p.category, []).append(p)

    cases = []
    for cat, items in sorted(by_cat.items()):
        step = max(1, len(items) // SAMPLE_PER_CATEGORY)
        for p in items[::step][:SAMPLE_PER_CATEGORY]:
            rk = p.rag_knowledge
            if rk and rk.official_faq:
                cases.append({"type": "faq", "query": rk.official_faq[0].question,
                              "expect_pid": p.product_id, "category": cat})
            cases.append({"type": "title", "query": f"{p.brand}{p.sub_category}",
                          "expect_pid": p.product_id, "category": cat})
    return cases


async def run(tag: str, with_rerank: bool = False, hybrid: bool | None = None) -> dict:
    from app.repositories.product_repo import get_product_repo
    from app.retrieval.semantic_retriever import SemanticRetriever
    from app.core.config import CHUNK_COLLECTION_NAME

    # --hybrid / --no-hybrid 进程内覆盖开关（spec §5.1）：对比 dense vs dense+BM25
    # 对同一集合的 faq/title hit@1 影响。默认 None = 跟随配置。
    if hybrid is not None:
        import app.core.config as _cfg

        _cfg.ENABLE_HYBRID_RETRIEVAL = hybrid

    retriever = SemanticRetriever(get_product_repo())
    reranker = None
    if with_rerank:
        from app.providers.recall.rerank_fusion import RerankFusion

        reranker = RerankFusion()
    cases = build_cases()
    from app.core.config import ENABLE_HYBRID_RETRIEVAL as _hyb

    print(f"集合={CHUNK_COLLECTION_NAME}  用例={len(cases)} 条  "
          f"rerank={'on' if with_rerank else 'off'}  hybrid={'on' if _hyb else 'off'}")

    def _new_stat():
        return {"h1": 0, "h5": 0, "mrr": 0.0, "n": 0}

    stats = {"faq": _new_stat(), "title": _new_stat()}
    rr_stats = {"faq": _new_stat(), "title": _new_stat()}
    misses = []
    t0 = time.perf_counter()

    def _score(stat: dict, pids: list[str], expect: str):
        stat["n"] += 1
        if expect in pids:
            rank = pids.index(expect) + 1
            stat["mrr"] += 1.0 / rank
            if rank == 1:
                stat["h1"] += 1
            if rank <= 5:
                stat["h5"] += 1
            return rank
        return None

    for i, c in enumerate(cases, 1):
        try:
            results = await retriever._chunk_search_impl(  # noqa: SLF001 — 绕缓存保证对比公平
                c["query"], TOP_K, None, None, None, None, "max_score")
        except Exception as e:  # noqa: BLE001
            results = []
            print(f"  ! case {i} error: {e}")
        pids = [r["product_id"] for r in results]
        rank = _score(stats[c["type"]], pids, c["expect_pid"])
        if rank is None:
            misses.append({"type": c["type"], "query": c["query"][:40],
                           "expect": c["expect_pid"], "got": pids[:3]})

        if reranker is not None and results:
            # 与主链 graph._node_reranker 同口径：头 8 精排，尾部拼接
            head, tail = results[:8], results[8:]
            try:
                ranked = await reranker.rerank(query=c["query"], products=head,
                                               evidence=[], visual_matched_pids=[])
                rr_pids = [r["product_id"] for r in ranked + tail]
            except Exception as e:  # noqa: BLE001
                print(f"  ! rerank case {i} error: {e}")
                rr_pids = pids
            _score(rr_stats[c["type"]], rr_pids, c["expect_pid"])

        if i % 32 == 0:
            print(f"  {i}/{len(cases)}")

    report = {"tag": tag, "collection": CHUNK_COLLECTION_NAME, "cases": len(cases),
              "elapsed_s": round(time.perf_counter() - t0, 1)}
    for typ, s in stats.items():
        n = max(s["n"], 1)
        report[typ] = {"n": s["n"], "hit@1": round(s["h1"] / n, 3),
                       "hit@5": round(s["h5"] / n, 3), "mrr@10": round(s["mrr"] / n, 3)}
    if with_rerank:
        for typ, s in rr_stats.items():
            n = max(s["n"], 1)
            report[f"{typ}_reranked"] = {"n": s["n"], "hit@1": round(s["h1"] / n, 3),
                                          "hit@5": round(s["h5"] / n, 3),
                                          "mrr@10": round(s["mrr"] / n, 3)}
    report["misses_sample"] = misses[:10]
    report["miss_count"] = len(misses)
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--with-rerank", action="store_true",
                    help="额外输出精排后口径（与主链同样头 8 门控）")
    ap.add_argument("--hybrid", dest="hybrid", action="store_true", default=None,
                    help="强制开 dense+BM25 混合检索（需 V7 双向量集合）")
    ap.add_argument("--no-hybrid", dest="hybrid", action="store_false",
                    help="强制纯 dense（与 --hybrid 对照跑）")
    args = ap.parse_args()
    report = asyncio.run(run(args.tag, with_rerank=args.with_rerank, hybrid=args.hybrid))
    out = ROOT / "data" / "rag_eval_runs" / f"retrieval-{args.tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "misses_sample"},
                     ensure_ascii=False, indent=1))
    print(f"报告: {out}")


if __name__ == "__main__":
    main()
