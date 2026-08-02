"""子品类代表图 → 商品图片分发脚本。

背景：后四类（家居/母婴/运动户外/个护清洁）400 个商品原本 image_path 全部指向不存在的
文件（API `/api/products/{pid}/image` 无兜底，直接 404）。用 ImageGen 按「子品类」生成
电商级白底产品图（同一子品类的商品共用视觉），再分发到每个商品自己的文件名，
既保证 image_path 一一对应且文件真实存在，也保证图片与商品品类视觉相符。

用法：
    # 单个子品类分发
    python scripts/apply_subcategory_images.py --map "砧板=/path/to/gen.png"
    # 批量（清单文件，键为子品类，值为源图路径）
    python scripts/apply_subcategory_images.py --manifest data/subcategory_image_manifest.json
    # 查看当前缺图统计
    python scripts/apply_subcategory_images.py --report
"""

from __future__ import annotations

import argparse
import glob
import json
from collections import defaultdict
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "ecommerce_agent_dataset"
MANIFEST = ROOT / "data" / "subcategory_image_manifest.json"

TARGET_DIRS = ["1_美妆护肤", "2_数码电子", "3_服饰运动", "4_食品生活",
               "5_家居用品", "6_母婴用品", "7_运动户外", "8_个护清洁"]
JPEG_SIZE = (900, 900)
JPEG_QUALITY = 88


def index_products() -> dict[str, list[tuple[Path, dict]]]:
    """sub_category -> [(json 路径, 商品体)]"""
    idx: dict[str, list[tuple[Path, dict]]] = defaultdict(list)
    for d in TARGET_DIRS:
        for f in sorted(glob.glob(str(BASE / d / "data" / "*.json"))):
            p = json.loads(Path(f).read_text(encoding="utf-8"))
            idx[p.get("sub_category", "")].append((Path(f), p))
    return idx


def missing_report(idx: dict[str, list[tuple[Path, dict]]]) -> dict[str, dict]:
    """统计每个子品类缺图数量（按品类目录分组）。"""
    out: dict[str, dict] = {}
    for sub, items in sorted(idx.items()):
        miss = [(f, p) for f, p in items if not (BASE / p["image_path"]).exists()]
        if miss:
            cat = miss[0][1]["category"]
            out[sub] = {"category": cat, "missing": len(miss), "total": len(items)}
    return out


def distribute(sub: str, src: Path, idx: dict[str, list[tuple[Path, dict]]],
               overwrite: bool = False) -> int:
    """把 src 图转成 JPEG 分发到该子品类下所有缺图商品的 image_path。"""
    items = idx.get(sub) or []
    if not items:
        print(f"  ! 子品类无商品: {sub}")
        return 0
    if not src.exists():
        print(f"  ! 源图不存在: {src}")
        return 0

    im = Image.open(src).convert("RGB")
    im.thumbnail(JPEG_SIZE, Image.LANCZOS)

    n = 0
    for f, p in items:
        # image_path 统一规范为 {dir}/images/{pid}.jpg
        cat_dir = f.parent.parent.name
        rel = f"{cat_dir}/images/{p['product_id']}.jpg"
        dest = BASE / rel
        if dest.exists() and not overwrite:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        im.save(dest, "JPEG", quality=JPEG_QUALITY, optimize=True)
        if p.get("image_path") != rel:
            p["image_path"] = rel
            f.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", nargs="*", default=[], help='形如 "子品类=源图路径"')
    ap.add_argument("--manifest", default="")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--save-manifest", action="store_true",
                    help="把本次 --map 合并进 data/subcategory_image_manifest.json")
    args = ap.parse_args()

    idx = index_products()

    if args.report:
        rep = missing_report(idx)
        by_cat: dict[str, list[str]] = defaultdict(list)
        for sub, info in rep.items():
            by_cat[info["category"]].append(f"{sub}({info['missing']})")
        total = sum(v["missing"] for v in rep.values())
        for cat, subs in sorted(by_cat.items()):
            print(f"[{cat}] 缺图子品类 {len(subs)} 个: {' '.join(sorted(subs))}")
        print(f"\n总缺图商品 {total} 个，涉及 {len(rep)} 个子品类")
        return

    pairs: dict[str, str] = {}
    if args.manifest:
        pairs.update(json.loads(Path(args.manifest).read_text(encoding="utf-8")))
    for item in args.map:
        if "=" in item:
            k, v = item.split("=", 1)
            pairs[k.strip()] = v.strip()

    if not pairs:
        print("未提供 --map 或 --manifest")
        return

    total = 0
    for sub, src in pairs.items():
        n = distribute(sub, Path(src), idx, args.overwrite)
        total += n
        print(f"  {sub}: 写入 {n} 张")
    print(f"\n共写入 {total} 张图片")

    if args.save_manifest:
        existing = {}
        if MANIFEST.exists():
            existing = json.loads(MANIFEST.read_text(encoding="utf-8"))
        existing.update(pairs)
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps(existing, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"清单已更新: {MANIFEST}（累计 {len(existing)} 个子品类）")


if __name__ == "__main__":
    main()
