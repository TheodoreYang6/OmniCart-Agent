"""数据集质量校验器 —— 以 p_beauty_001.json 为金标准的可量化量尺。

金标准特征（1_美妆护肤/data/p_beauty_001.json）：
- title 35 字，含品牌 + 产品全名 + 功效关键词 + 规格
- base_price 720.0，与子品类真实价位相符
- image_path 指向真实存在的文件
- skus 3 条，规格维度有意义，**价格阶梯递增**（720/980/1260）
- marketing_description 207 字：定位→核心成分机理→辅助成分→适合人群→使用方法→注意事项
- official_faq 3 条，问题针对该商品（成分作用/规格怎么选/敏感肌适用），答案 100-170 字
- user_reviews 5 条，真实中文姓名，评分有差异且含真实负面，内容含具体价格/用法/时长/结果

用法：
    PYTHONPATH=backend python scripts/validate_dataset.py                 # 全量
    PYTHONPATH=backend python scripts/validate_dataset.py --dirs 5_家居用品
    PYTHONPATH=backend python scripts/validate_dataset.py --verbose --limit 5
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "ecommerce_agent_dataset"
sys.path.insert(0, str(ROOT / "scripts"))

from dataset_kb import SUB_KB  # noqa: E402

ALL_DIRS = ["1_美妆护肤", "2_数码电子", "3_服饰运动", "4_食品生活",
            "5_家居用品", "6_母婴用品", "7_运动户外", "8_个护清洁"]

# 金标准阈值（略低于 p_beauty_001 实测值，留合理余量）
MIN_MARKETING = 150      # gold 207
MIN_FAQ = 3              # gold 3
MIN_FAQ_ANSWER = 80      # gold 100-170
MIN_REVIEWS = 5          # gold 5
MIN_REVIEW_LEN = 40      # gold 60-100
MIN_SKUS = 2             # gold 3
MIN_TITLE = 15           # gold 35

# 模板套话黑名单（generate_1000_products.py 时代的通用文案特征）
GENERIC_FAQ_Q = [
    "这款产品适合什么人群？", "质量怎么样？", "售后怎么样？",
    "适合什么人群", "有什么特点",
]
GENERIC_PHRASES = [
    "适合大部分人群使用，具体可根据个人需求选择合适的规格型号",
    "品质保障，做工精良用料扎实，口碑良好",
    "支持7天无理由退换",
    "效果还行，手感很棒日常使用完全够了",
    "中规中矩吧",
]
# 与商品无关的模板昵称（如"数码控"点评砧板）
TEMPLATE_NICKNAMES = {"颜值控", "数码控", "小柚", "洁癖患者", "剁手党", "购物达人",
                      "品质控", "性价比之王", "老顾客", "路人甲"}


def check_product(p: dict, rel_path: str) -> list[str]:
    """返回违规项列表；空列表 = 达标。"""
    errs: list[str] = []
    sub = p.get("sub_category") or ""
    kb = SUB_KB.get(sub)

    # ---- 1. 必填字段 ----
    for k in ("product_id", "title", "brand", "category", "sub_category",
              "base_price", "image_path", "skus", "rag_knowledge"):
        if not p.get(k):
            errs.append(f"missing:{k}")
    if errs:
        return errs

    # ---- 2. 标题 ----
    title = p["title"]
    if len(title) < MIN_TITLE:
        errs.append(f"title_short:{len(title)}")
    if p["brand"] not in title:
        errs.append("title_no_brand")

    # ---- 3. 价格合理性 ----
    price = float(p["base_price"])
    if price <= 0:
        errs.append("price_nonpositive")
    elif kb:
        lo, hi = kb["price"]
        # 允许 base_price 落在区间内（上界给 1.6x 余量容纳高配基准款）
        if not (lo * 0.6 <= price <= hi * 1.6):
            errs.append(f"price_out_of_range:{price}not_in[{lo},{hi}]")

    # ---- 4. 品牌与子品类相符 ----
    if kb and p["brand"] not in kb["brands"]:
        errs.append(f"brand_not_in_kb:{p['brand']}@{sub}")

    # ---- 5. SKU ----
    skus = p["skus"]
    if len(skus) < MIN_SKUS:
        errs.append(f"sku_lt{MIN_SKUS}:{len(skus)}")
    sku_ids = [s.get("sku_id") for s in skus]
    if len(set(sku_ids)) != len(sku_ids):
        errs.append("sku_id_dup")
    if any(not (s.get("properties") or {}) for s in skus):
        errs.append("sku_no_properties")
    # V6：规格维度 key 必须含中文（纯 ASCII key 如 color/type 属 LLM 产出残留，防回归）
    for s in skus:
        for k in (s.get("properties") or {}):
            if str(k).isascii():
                errs.append(f"sku_key_not_cn:{k}")
                break
        else:
            continue
        break
    sku_prices = [float(s.get("price") or 0) for s in skus]
    if any(x <= 0 for x in sku_prices):
        errs.append("sku_price_nonpositive")
    elif len(set(sku_prices)) == 1 and len(skus) > 1:
        errs.append("sku_price_flat")  # 金标准是阶梯价 720/980/1260
    if sku_prices and abs(min(sku_prices) - price) > 0.01:
        errs.append("base_price_ne_min_sku")

    # ---- 6. 图片存在 ----
    ip = p["image_path"]
    if not (BASE / ip).exists():
        errs.append("image_file_missing")

    rk = p["rag_knowledge"]

    # ---- 7. 营销描述 ----
    md = rk.get("marketing_description") or ""
    if len(md) < MIN_MARKETING:
        errs.append(f"marketing_short:{len(md)}")
    if p["brand"] not in md:
        errs.append("marketing_no_brand")
    for ph in GENERIC_PHRASES:
        if ph in md:
            errs.append("marketing_generic")
            break

    # ---- 8. FAQ ----
    faqs = rk.get("official_faq") or []
    if len(faqs) < MIN_FAQ:
        errs.append(f"faq_lt{MIN_FAQ}:{len(faqs)}")
    qs = [f.get("question", "") for f in faqs]
    if len(set(qs)) != len(qs):
        errs.append("faq_q_dup")
    if any(q.strip() in GENERIC_FAQ_Q for q in qs):
        errs.append("faq_generic")
    short_ans = [len(f.get("answer", "")) for f in faqs if len(f.get("answer", "")) < MIN_FAQ_ANSWER]
    if short_ans:
        errs.append(f"faq_answer_short:{short_ans}")

    # ---- 9. 用户评价 ----
    revs = rk.get("user_reviews") or []
    if len(revs) < MIN_REVIEWS:
        errs.append(f"reviews_lt{MIN_REVIEWS}:{len(revs)}")
    nicks = [r.get("nickname", "") for r in revs]
    if len(set(nicks)) != len(nicks):
        errs.append("review_nick_dup")
    if set(nicks) & TEMPLATE_NICKNAMES:
        errs.append(f"review_nick_template:{sorted(set(nicks) & TEMPLATE_NICKNAMES)}")
    ratings = [r.get("rating") for r in revs]
    if any(not isinstance(x, int) or not (1 <= x <= 5) for x in ratings):
        errs.append("review_rating_invalid")
    elif len(set(ratings)) < 2:
        errs.append("review_rating_uniform")  # 金标准 1,2,5,2,1 有差异
    contents = [r.get("content", "") for r in revs]
    if any(len(c) < MIN_REVIEW_LEN for c in contents):
        errs.append(f"review_content_short:{[len(c) for c in contents]}")
    if len(set(contents)) != len(contents):
        errs.append("review_content_dup")
    for c in contents:
        if any(ph in c for ph in GENERIC_PHRASES):
            errs.append("review_generic")
            break

    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dirs", nargs="*", default=ALL_DIRS)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()

    grand_total = grand_pass = 0
    all_err_counter: Counter = Counter()
    failing: dict[str, list[str]] = {}

    for d in args.dirs:
        files = sorted(glob.glob(str(BASE / d / "data" / "*.json")))
        n = ok = 0
        errc: Counter = Counter()
        for f in files:
            n += 1
            rel = os.path.relpath(f, BASE)
            try:
                p = json.load(open(f, encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                errc[f"json_parse_error"] += 1
                failing[rel] = [f"json_parse_error:{e}"]
                continue
            errs = check_product(p, rel)
            if errs:
                failing[rel] = errs
                for e in errs:
                    errc[e.split(":")[0]] += 1
            else:
                ok += 1
        grand_total += n
        grand_pass += ok
        all_err_counter.update(errc)
        rate = ok / n * 100 if n else 0
        print(f"[{d}] {ok}/{n} 达标 ({rate:.1f}%)  " +
              " ".join(f"{k}={v}" for k, v in errc.most_common(6)))

    print(f"\n=== 总计 {grand_pass}/{grand_total} 达标 "
          f"({grand_pass / grand_total * 100 if grand_total else 0:.1f}%) ===")
    print("Top 违规类型:", dict(all_err_counter.most_common(12)))

    if args.verbose:
        print("\n--- 违规样例 ---")
        for rel, errs in list(failing.items())[:args.limit]:
            print(f"  {rel}: {errs}")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"total": grand_total, "passed": grand_pass,
                        "errors": dict(all_err_counter), "failing": failing},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n报告: {args.json_out}")

    return 0 if grand_pass == grand_total else 1


if __name__ == "__main__":
    sys.exit(main())
