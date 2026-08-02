"""结构性问题手术式修复 —— 不动文案，只修可确定性计算的字段。

用于保护「人工精修的金标准商品」（前四类 001-025）：它们文案已达标，只在结构项上
有历史遗留问题（base_price 与最低 SKU 价不一致、SKU 同价无阶梯、品牌不在真实词表），
用 LLM 重写会丢掉人工内容，因此这里只做确定性修复：

1. base_price != min(sku.price) -> base_price 对齐最低 SKU 价
2. SKU 同价（无阶梯）-> 按规格顺序生成 +8%/+15% 阶梯价（金标准 720/980/1260 的形态）
3. sku_id 重复 -> 按序重排
4. properties 为空 -> 用知识库规格维度补一个占位规格

用法：
    python scripts/fix_structural.py --dirs 1_美妆护肤 2_数码电子 3_服饰运动 4_食品生活
    python scripts/fix_structural.py --dry-run
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "ecommerce_agent_dataset"
sys.path.insert(0, str(ROOT / "scripts"))

from dataset_kb import SUB_KB  # noqa: E402

ALL_DIRS = ["1_美妆护肤", "2_数码电子", "3_服饰运动", "4_食品生活",
            "5_家居用品", "6_母婴用品", "7_运动户外", "8_个护清洁"]

# V6：SKU 规格维度英文 key 归一（LLM 富化时少量产出英文 key，影响展示与规格入向量）
SKU_KEY_CN = {
    "color": "颜色", "type": "类型", "resolution": "分辨率", "length": "长度",
    "thickness": "厚度", "height": "高度", "refresh_rate": "刷新率",
    "memory/harddisk": "内存/硬盘", "memory/hard_disk": "内存/硬盘",
}


def fix_product(p: dict) -> list[str]:
    """就地修复，返回修复项列表。"""
    fixed: list[str] = []
    pid = p.get("product_id", "")
    kb = SUB_KB.get(p.get("sub_category", ""))
    skus = p.get("skus") or []
    if not skus:
        return fixed

    # 1. sku_id 规范化去重
    want_ids = [f"s_{pid}_{i}" for i in range(1, len(skus) + 1)]
    if [s.get("sku_id") for s in skus] != want_ids:
        for s, sid in zip(skus, want_ids):
            s["sku_id"] = sid
        fixed.append("sku_id")

    # 2. properties 补齐 + 英文 key 归一（V6）
    dim = (kb["dims"][0] if kb else "规格")
    for i, s in enumerate(skus, 1):
        props = s.get("properties") or {}
        renamed = {}
        for k, v in props.items():
            nk = SKU_KEY_CN.get(str(k).strip().lower(), k)
            renamed[nk] = v
        if renamed != props:
            s["properties"] = renamed
            fixed.append("sku_key_cn")
        if not (s.get("properties") or {}):
            s["properties"] = {dim: f"规格{i}"}
            fixed.append("sku_properties")

    # 3. 价格阶梯（同价 -> 递增；金标准形态 720/980/1260）
    prices = [float(s.get("price") or 0) for s in skus]
    if any(x <= 0 for x in prices):
        base = float(p.get("base_price") or 0) or 99.0
        prices = [round(base * (1 + 0.15 * i), 2) for i in range(len(skus))]
        fixed.append("sku_price_nonpositive")
    if len(set(prices)) == 1 and len(skus) > 1:
        anchor = prices[0]
        prices = [anchor] + [round(anchor * (1 + 0.18 * i), 2) for i in range(1, len(skus))]
        fixed.append("sku_price_flat")
    # 严格递增
    for i in range(1, len(prices)):
        if prices[i] <= prices[i - 1]:
            prices[i] = round(prices[i - 1] * 1.08 + 1, 2)
            fixed.append("sku_price_order")
    for s, pr in zip(skus, prices):
        s["price"] = pr

    # 4. base_price 对齐最低 SKU 价
    lo = min(prices)
    if abs(float(p.get("base_price") or 0) - lo) > 0.01:
        p["base_price"] = lo
        fixed.append("base_price_align")

    return fixed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dirs", nargs="*", default=ALL_DIRS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    total = touched = 0
    counter: Counter = Counter()
    for d in args.dirs:
        for f in sorted(glob.glob(str(BASE / d / "data" / "*.json"))):
            total += 1
            path = Path(f)
            p = json.loads(path.read_text(encoding="utf-8"))
            fixed = fix_product(p)
            if fixed:
                touched += 1
                counter.update(fixed)
                if not args.dry_run:
                    path.write_text(json.dumps(p, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    print(f"扫描 {total} 个商品，修复 {touched} 个"
          f"{'（dry-run 未写入）' if args.dry_run else ''}")
    print("修复项:", dict(counter.most_common()))


if __name__ == "__main__":
    main()
