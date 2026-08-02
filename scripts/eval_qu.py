"""QU V2 离线评测：意图准确率 / 拆分组数与角色 P/R / 品类与预算抽取准确率。

用法：
    PYTHONPATH=backend python scripts/eval_qu.py                # 全量 40 条
    PYTHONPATH=backend python scripts/eval_qu.py --limit 10

评测对象是 `aunderstand_query`（QU LLM 层，评 prompt 质量；规则融合兜底另有单测覆盖）。
MOCK 模式可跑通管线验证；真实 key 下产出真基线。结果落 data/eval_runs/qu-{ts}.json。
口径：
- intent: 完全相等
- 拆分: 期望拆( roles 非空)时，预测组数相等 & role 模糊命中(子串双向)算对；期望不拆时预测 sub_queries 为空算对
- category/budget: 仅期望非空的样本计入统计
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.agents.router_agent import aunderstand_query, validate_sub_queries  # noqa: E402


def _role_match(pred_roles: list[str], exp_roles: list[str]) -> bool:
    if len(pred_roles) != len(exp_roles):
        return False
    hit = 0
    used = set()
    for e in exp_roles:
        for i, p in enumerate(pred_roles):
            if i in used:
                continue
            if e in p or p in e:
                used.add(i)
                hit += 1
                break
    return hit == len(exp_roles)


async def run(limit: int | None) -> dict:
    dataset = json.loads((ROOT / "data" / "qu_eval_dataset.json").read_text(encoding="utf-8"))
    cases = dataset["cases"][:limit] if limit else dataset["cases"]

    n = len(cases)
    intent_ok = 0
    split_total = split_ok = 0
    nosplit_total = nosplit_ok = 0
    cat_total = cat_ok = 0
    budget_total = budget_ok = 0
    details = []

    for case in cases:
        exp = case["expected"]
        try:
            qu = await aunderstand_query(case["query"], case.get("context", ""))
        except Exception as e:  # noqa: BLE001
            qu = {"_error": str(e)}
        pred_intent = qu.get("intent")
        pred_sq = validate_sub_queries(qu.get("sub_queries"))
        pred_roles = [s.role or s.query for s in pred_sq]

        i_ok = pred_intent == exp["intent"]
        intent_ok += i_ok

        exp_roles = exp.get("sub_query_roles") or []
        if exp_roles:
            split_total += 1
            s_ok = _role_match(pred_roles, exp_roles)
            split_ok += s_ok
        else:
            nosplit_total += 1
            s_ok = not pred_roles  # 禁止为拆而拆
            nosplit_ok += s_ok

        c_ok = None
        if exp.get("category"):
            cat_total += 1
            c_ok = qu.get("category") == exp["category"]
            cat_ok += bool(c_ok)
        b_ok = None
        if exp.get("budget_max") is not None:
            budget_total += 1
            try:
                b_ok = float(qu.get("budget_max") or 0) == float(exp["budget_max"])
            except (TypeError, ValueError):
                b_ok = False
            budget_ok += bool(b_ok)

        details.append({
            "id": case["id"], "query": case["query"],
            "expected_intent": exp["intent"], "pred_intent": pred_intent,
            "intent_ok": i_ok, "expected_roles": exp_roles, "pred_roles": pred_roles,
            "split_ok": s_ok, "category_ok": c_ok, "budget_ok": b_ok,
        })

    report = {
        "ts": int(time.time()), "cases": n,
        "intent_acc": round(intent_ok / n, 3) if n else 0,
        "split_recall": round(split_ok / split_total, 3) if split_total else None,
        "no_split_precision": round(nosplit_ok / nosplit_total, 3) if nosplit_total else None,
        "category_acc": round(cat_ok / cat_total, 3) if cat_total else None,
        "budget_acc": round(budget_ok / budget_total, 3) if budget_total else None,
        "details": details,
    }
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    report = asyncio.run(run(args.limit))
    out_dir = ROOT / "data" / "eval_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"qu-{report['ts']}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"QU V2 评测（{report['cases']} 条）")
    print(f"  意图准确率        : {report['intent_acc']}")
    print(f"  拆分召回(应拆样本): {report['split_recall']}")
    print(f"  不拆精度(禁为拆而拆): {report['no_split_precision']}")
    print(f"  品类准确率        : {report['category_acc']}")
    print(f"  预算准确率        : {report['budget_acc']}")
    bad = [d for d in report["details"] if not d["intent_ok"] or not d["split_ok"]]
    if bad:
        print(f"  badcase {len(bad)} 条: {[d['id'] for d in bad]}")
    print(f"  报告: {out}")


if __name__ == "__main__":
    main()
