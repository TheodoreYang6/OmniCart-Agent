#!/usr/bin/env python3
"""子品类纯度评测 —— 混合检索（dense+BM25）vs 纯 dense 对照。

spec: 混合检索与四bug根治 §5.1

背景（实测坐实）：纯语义检索对口语泛化 query 会语义漂移——
"适合敏感肌的补水产品" 曾召回口红、"换季泛红用什么好" 全给面霜/精华。
BM25 词面侧把品类词权重顶住，与 dense 互补（服务端 RRF 融合）。

指标：
- purity@5：top5 中属于期望子品类集合的比例（主指标）
- off_topic：召回到明显无关子品类（如护肤 query 命中口红/彩妆）的用例数
- 同时输出同款折叠生效数（variant_count > 0 的结果数）

用法（后端无需启动，直连检索层）：
    PYTHONPATH=backend python scripts/eval_subcategory_purity.py --tag v7_hybrid
    # 对照：临时切集合名跑纯 dense
    OMNICART_CHUNK_COLLECTION=product_chunks_v6_1024 PYTHONPATH=backend \
        python scripts/eval_subcategory_purity.py --tag v6_dense
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP_K = 5

# 易混子品类专项用例：query → 可接受的子品类集合（宽松取并集，避免过严）
# off_topic：一旦命中即判定语义漂移（与 query 领域完全无关）
CASES: list[dict] = [
    # —— 护肤：面膜 vs 面霜/精华（用户实际反馈的串味）——
    {"q": "面膜", "ok": {"面膜"}, "off": {"口红", "唇釉", "腮红", "粉饼", "蜜粉"}},
    {"q": "面膜类型的产品推荐", "ok": {"面膜"}, "off": {"口红", "唇釉", "腮红", "粉饼"}},
    {"q": "补水面膜哪个好", "ok": {"面膜"}, "off": {"口红", "唇釉", "腮红"}},
    {"q": "洗面奶推荐", "ok": {"洁面", "洁面膏", "洗面奶"}, "off": {"口红", "腮红", "洗手液"}},
    {"q": "适合敏感肌的补水产品", "ok": {"面膜", "面霜", "精华", "化妆水", "乳液"},
     "off": {"口红", "唇釉", "腮红", "粉饼", "蜜粉", "洗手液", "洗发水"}},
    {"q": "换季泛红用什么好", "ok": {"面膜", "面霜", "精华", "化妆水", "乳液"},
     "off": {"口红", "唇釉", "腮红", "粉饼", "洗发水"}},
    {"q": "干皮急救好物", "ok": {"面膜", "面霜", "精华", "化妆水", "乳液", "身体乳"},
     "off": {"口红", "唇釉", "腮红", "粉饼"}},
    {"q": "抗老精华", "ok": {"精华"}, "off": {"口红", "腮红", "洗发水", "洗手液"}},
    # —— 个护：洗发水 vs 洗手液/沐浴露 ——
    {"q": "洗发水", "ok": {"洗发水"}, "off": {"洗手液", "面膜", "口红", "精华"}},
    {"q": "去屑洗发水推荐", "ok": {"洗发水"}, "off": {"洗手液", "面膜", "口红"}},
    {"q": "洗手液", "ok": {"洗手液"}, "off": {"洗发水", "面膜", "精华"}},
    # —— 数码：耳机 vs 充电宝/音箱 ——
    {"q": "降噪耳机", "ok": {"蓝牙耳机", "耳机", "真无线耳机", "头戴式耳机"},
     "off": {"充电宝", "移动电源", "面膜", "口红"}},
    {"q": "无线蓝牙耳机推荐", "ok": {"蓝牙耳机", "耳机", "真无线耳机", "头戴式耳机"},
     "off": {"充电宝", "移动电源", "数据线"}},
    {"q": "充电宝", "ok": {"充电宝", "移动电源"}, "off": {"蓝牙耳机", "耳机", "面膜"}},
    # —— 家居/母婴：保温杯 vs 儿童水杯 ——
    {"q": "保温杯", "ok": {"保温杯", "儿童水杯"}, "off": {"面膜", "耳机", "洗发水"}},
    {"q": "儿童保温水杯", "ok": {"儿童水杯", "保温杯"}, "off": {"面膜", "耳机"}},
    # —— 运动户外：登山鞋/登山杖 ——
    {"q": "登山鞋", "ok": {"登山鞋", "徒步鞋", "越野跑鞋"}, "off": {"面膜", "耳机", "登山杖"}},
    {"q": "登山杖", "ok": {"登山杖"}, "off": {"登山鞋", "面膜", "耳机"}},
    {"q": "跑步鞋推荐", "ok": {"跑步鞋", "运动鞋", "越野跑鞋", "跑鞋"},
     "off": {"面膜", "耳机", "登山杖"}},
    # —— 食品 ——
    {"q": "咖啡豆", "ok": {"咖啡", "咖啡豆", "挂耳咖啡"}, "off": {"面膜", "耳机", "洗发水"}},
    {"q": "茶叶推荐", "ok": {"茶叶", "茶饮"}, "off": {"咖啡", "面膜", "耳机"}},
    {"q": "酸奶", "ok": {"酸奶", "牛奶"}, "off": {"面膜", "耳机", "洗发水"}},
    {"q": "坚果零食", "ok": {"坚果", "坚果/零食", "零食", "果干", "肉干"},
     "off": {"面膜", "耳机", "洗发水"}},
    # —— 数码补充（易混：平板 vs 笔记本 vs 手机）——
    {"q": "平板电脑", "ok": {"平板电脑"}, "off": {"笔记本电脑", "智能手机", "面膜"}},
    {"q": "笔记本电脑推荐", "ok": {"笔记本电脑"}, "off": {"平板电脑", "智能手机"}},
    {"q": "智能手表", "ok": {"智能手表", "智能手环"}, "off": {"面膜", "耳机"}},
    # —— 服饰与家居补充 ——
    {"q": "羽绒服", "ok": {"羽绒服"}, "off": {"面膜", "耳机", "跑步鞋"}},
    {"q": "连衣裙", "ok": {"连衣裙", "半身裙"}, "off": {"面膜", "耳机"}},
    {"q": "台灯", "ok": {"台灯", "落地灯"}, "off": {"面膜", "耳机", "洗发水"}},
    {"q": "纸尿裤", "ok": {"纸尿裤", "婴儿湿巾"}, "off": {"面膜", "耳机", "洗发水"}},
]


async def run(tag: str) -> dict:
    from app.core.config import CHUNK_COLLECTION_NAME
    from app.repositories.product_repo import get_product_repo
    from app.retrieval.semantic_retriever import SemanticRetriever

    repo = get_product_repo()
    r = SemanticRetriever(repo)
    print(f"集合={CHUNK_COLLECTION_NAME}  用例={len(CASES)} 条  top_k={TOP_K}")

    # 库存盘点：部分品类数据集里本就不足 5 款（如洁面仅 1 款、洗发水 4 款），
    # raw purity@5 存在数学上限（洗面奶永远不可能超 0.2）。故同时算
    # purity_adj = hit / min(top_k, 库存数) ——"库里有的都召回了吗"，作为主门槛。
    inventory: dict[str, int] = {}
    for p in repo.list_all():
        sub = getattr(p, "sub_category", "") or ""
        inventory[sub] = inventory.get(sub, 0) + 1

    rows = []
    pur_sum = 0.0
    adj_sum = 0.0
    off_cases = 0
    variant_folded = 0
    t0 = time.perf_counter()

    for c in CASES:
        try:
            res = await r._chunk_search_impl(  # noqa: SLF001 — 绕缓存保证对比公平
                c["q"], TOP_K, None, None, None, None, "max_score")
        except Exception as e:  # noqa: BLE001
            rows.append({"query": c["q"], "error": str(e)[:80]})
            continue
        subs = []
        for p in res:
            prod = repo.get_by_id(p.get("product_id", ""))
            subs.append(prod.sub_category if prod else "?")
            if p.get("variant_count"):
                variant_folded += 1
        hit = sum(1 for s in subs if s in c["ok"])
        purity = hit / max(len(subs), 1)
        avail = sum(inventory.get(s, 0) for s in c["ok"])
        purity_adj = hit / max(min(TOP_K, avail), 1)
        offs = [s for s in subs if s in c["off"]]
        pur_sum += purity
        adj_sum += min(purity_adj, 1.0)
        if offs:
            off_cases += 1
        rows.append({"query": c["q"], "purity": round(purity, 3),
                     "purity_adj": round(min(purity_adj, 1.0), 3), "available": avail,
                     "subs": subs, "off_topic": offs})
        flag = "OFF" if offs else ("OK " if purity_adj >= 0.8 else "low")
        print(f"  {flag} raw={purity:.2f} adj={min(purity_adj,1.0):.2f} "
              f"(库存{avail}) {c['q'][:16]:<18} {subs}")

    report = {
        "tag": tag,
        "collection": CHUNK_COLLECTION_NAME,
        "cases": len(CASES),
        "purity_at_5": round(pur_sum / max(len(CASES), 1), 3),
        "purity_at_5_inventory_adjusted": round(adj_sum / max(len(CASES), 1), 3),
        "off_topic_cases": off_cases,
        "variant_folded_results": variant_folded,
        "elapsed_s": round(time.perf_counter() - t0, 1),
        "details": rows,
    }
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    args = ap.parse_args()
    rep = asyncio.run(run(args.tag))
    out = ROOT / "data" / "rag_eval_runs" / f"purity-{args.tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\npurity@5(raw)={rep['purity_at_5']}  "
          f"purity@5(库存归一)={rep['purity_at_5_inventory_adjusted']}  "
          f"off_topic={rep['off_topic_cases']}/{rep['cases']}"
          f"  同款折叠={rep['variant_folded_results']}")
    print(f"报告: {out}")


if __name__ == "__main__":
    main()
