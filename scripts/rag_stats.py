"""RAG 评测统计脚本。从 rag_traces.jsonl 计算各项指标。"""
import json
import sys
from pathlib import Path


def compute(traces_file: str = "data/rag_traces.jsonl"):
    path = Path(traces_file)
    if not path.exists():
        print(f"File not found: {traces_file}")
        return

    lines = path.read_text("utf-8").strip().split("\n")
    traces = [json.loads(l) for l in lines if l.strip()]

    print(f"Total queries: {len(traces)}")
    print(f"With golden eval: {sum(1 for t in traces if t.get('evaluation'))}")
    print()

    eval_traces = [t for t in traces if t.get("evaluation")]
    if not eval_traces:
        print("No eval data. Add golden product_ids to eval_queries.json")
        return

    metrics = [
        "hit@1", "hit@3", "hit@5", "mrr",
        "recall@5", "recall@10", "precision@1", "precision@3",
    ]
    for m in metrics:
        vals = [t["evaluation"].get(m, 0) for t in eval_traces if t["evaluation"].get(m) is not None]
        if vals:
            avg = sum(vals) / len(vals)
            print(f"  {m:15s}: {avg:.4f}  (n={len(vals)})")

    print()
    print("Per-query details:")
    for t in eval_traces:
        q = t["query"][:50]
        ev = t.get("evaluation", {})
        print(f"  {q:50s} | hit@1={ev.get('hit@1',0)} hit@3={ev.get('hit@3',0)} mrr={ev.get('mrr',0)}")


def show_last(n: int = 3):
    """显示最近 N 条 trace 的候选变化。"""
    path = Path("data/rag_traces.jsonl")
    if not path.exists():
        return
    lines = path.read_text("utf-8").strip().split("\n")
    traces = [json.loads(l) for l in lines if l.strip()]

    for t in traces[-n:]:
        print(f"\n{'='*60}")
        print(f"Query: {t['query'][:80]}")
        print(f"Time: {t['timestamp']}")

        emb = t.get("embedding", {})
        print(f"\n--- Embedding (top 5/{len(emb.get('candidates',[]))}) ---")
        for c in emb.get("candidates", [])[:5]:
            print(f"  #{c['rank']} {c['product_id']} {c['brand']} {c['title'][:40]} | score={c['score']}")

        rer = t.get("reranker", {})
        print(f"\n--- Reranker (top 5/{rer.get('input_count',0)}) ---")
        for i, c in enumerate(rer.get("candidates", [])[:5]):
            s = rer.get("scores", [])[i] if i < len(rer.get("scores", [])) else 0
            print(f"  #{c['rank']} {c['product_id']} {c['brand']} {c['title'][:40]} | score={s}")

        fin = t.get("final_top5", [])
        print(f"\n--- Final Top 5 ---")
        for c in fin:
            print(f"  #{c['rank']} {c['product_id']} {c['brand']} {c['title'][:40]} | {c['display_score']}/10 {c['level']}")

        ev = t.get("evaluation", {})
        if ev:
            print(f"\n--- Eval ---")
            for k, v in ev.items():
                print(f"  {k}: {v}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "show":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
        show_last(n)
    elif len(sys.argv) > 1 and sys.argv[1] == "stats":
        compute()
    else:
        compute()
        print("\n--- Recent traces ---")
        show_last(3)
