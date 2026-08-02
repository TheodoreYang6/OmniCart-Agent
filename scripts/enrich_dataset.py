"""数据集富化管线 —— 用 Qwen 把商品补全到 p_beauty_001.json 金标准。

设计：
- 结构性字段（品牌/价格/SKU 规格维度）由 dataset_kb.py 真实知识库约束，避免 LLM 编造离谱价位；
- 文案字段（真实产品名/营销描述/FAQ/评价）由 Qwen 依金标准结构生成（LLM 持有真实电商商品知识）；
- 生成后立即用 validate_dataset.check_product 硬校验，不达标自动重试（最多 --retries 次）；
- 并发执行，失败不阻断（保留原文件），最终打印达标率。

用法：
    PYTHONPATH=backend python scripts/enrich_dataset.py --dirs 5_家居用品 --limit 3 --dry-run
    PYTHONPATH=backend python scripts/enrich_dataset.py --dirs 5_家居用品 6_母婴用品 7_运动户外 8_个护清洁
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "ecommerce_agent_dataset"
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from dataset_kb import SUB_KB  # noqa: E402
from validate_dataset import check_product  # noqa: E402

random.seed(42)

PROMPT = """你是资深电商商品内容运营，负责为真实在售商品撰写商品详情页数据。

# 商品基础信息（必须严格沿用，不得更改）
- 品类: {category}
- 子品类: {sub_category}
- 品牌: {brand}
- 价格区间: {lo}-{hi} 元（base_price 必须落在此区间内，符合该品类真实市场价）
- SKU 规格维度: {dims}

# 参考金标准（雅诗兰黛小棕瓶精华，学习其信息密度与写法，不要照抄内容）
- title: "雅诗兰黛特润修护肌活精华露淡纹紧致保湿夜间修护抗初老精华30ml"（品牌+产品全名+功效关键词+规格，25-40字）
- marketing_description（207字，六段式）: "雅诗兰黛特润修护肌活精华露（小棕瓶）是品牌经典抗初老单品，主打夜间肌底修护。核心成分含高浓度二裂酵母发酵产物溶胞物，能深入修护日间紫外线、污染造成的损伤…适合25+有干纹细纹、熬夜后暗沉的抗初老人群…建议每晚洁面爽肤后，取3-4滴掌心温热…注意开封后6个月内用完，敏感肌先做耳后测试。"
  → 结构: ①品牌定位与主打卖点 ②核心材质/技术及其原理 ③辅助特性 ④适合人群与场景 ⑤具体使用方法 ⑥注意事项
- official_faq（3条）: 问题必须针对本商品的具体技术/规格/适用性（如"核心成分X有什么作用""不同规格怎么选""敏感肌能用吗需注意什么"），禁止"这款产品适合什么人群""质量怎么样""售后怎么样"这类通用问题；每条答案100-170字，给出具体参数与操作建议。
- user_reviews（5 条）: 真实中文姓名昵称（如李小米、王梓涵、张雅静，每个商品用不同姓名）；内容 60-110 字，必须写出具体细节：具体价格、具体用了多久、具体使用方式、具体好或不好的结果。禁止"效果还行""中规中矩"这类空话。

# 评分分布硬要求（真实电商分布，不要每个商品都差评堆积）
- 5 条中 **3-4 条为好评（4-5 星）**，写出真实满意的具体原因；
- **必须有 1-2 条真实中差评（1-3 星）**，指出具体缺点（而非笼统吐槽），体现真实口碑不完美；
- 评分不得全部相同，且不同商品的评分组合要有差异（不要固定套用同一种分布）。

# 硬约束（违反则作废）
- title 必须以品牌名「{brand}」开头，且原文完整包含该品牌名（不得缩写、不得翻译、不得改写）；
- marketing_description 第一句必须出现完整品牌名「{brand}」；
- 若品牌名含英文（如 Britax宝得适），也要原样完整写出。

# 任务
为该品牌该子品类，选一个**真实在售的具体产品**（真实系列/型号名，不要编造不存在的产品），产出严格 JSON：

{{
  "title": "品牌（必须是「{brand}」）+真实产品全名+核心卖点关键词+规格，25-40字",
  "base_price": 数字（= 最低规格 SKU 的价格，落在 {lo}-{hi} 区间）,
  "skus": [
    {{"properties": {{"{dim0}": "具体规格值", "{dim1}": "具体规格值"}}, "price": 数字}},
    ... 共 3 条，properties 用给定的规格维度，price 按规格递增（如 720/980/1260），第一条 price 必须等于 base_price
  ],
  "marketing_description": "180-260字，首句必须含「{brand}」，严格按上述六段式，写出该品类真实的材质/工艺/技术参数",
  "official_faq": [
    {{"question": "针对本商品的具体问题", "answer": "100-170字具体解答"}},
    ... 共 3 条
  ],
  "user_reviews": [
    {{"nickname": "真实中文姓名", "rating": 1-5整数, "content": "60-110字，含具体价格/时长/用法/结果"}},
    ... 共 5 条，评分分化且含负面
  ]
}}

只输出 JSON，不要任何解释或 markdown 围栏。"""


# 仅靠 LLM 才能修的「文案类」违规前缀（结构类交由 fix_structural.py 手术修复，
# 避免把人工精修的金标准商品（前四类 001-025）文案重写掉）
CONTENT_ERR_PREFIXES = (
    "marketing_", "faq_", "review_", "reviews_", "title_",
)


def has_content_error(errs: list[str]) -> bool:
    return any(e.startswith(CONTENT_ERR_PREFIXES) for e in errs)


def _parse_json(raw: str) -> dict | None:
    raw = (raw or "").strip()
    if "```" in raw:
        parts = raw.split("```")
        for seg in parts:
            seg = seg.strip()
            if seg.startswith("json"):
                seg = seg[4:].strip()
            if seg.startswith("{"):
                raw = seg
                break
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return None


def _merge(orig: dict, gen: dict, brand: str, dims: list[str]) -> dict:
    """把 LLM 产出合并回商品记录，保持 product_id/category/image_path 契约。"""
    pid = orig["product_id"]
    skus_in = gen.get("skus") or []
    skus: list[dict] = []
    for i, s in enumerate(skus_in, 1):
        props = s.get("properties") or {}
        props = {k: str(v) for k, v in props.items() if v not in (None, "")}
        if not props:  # 兜底：至少一个规格维度
            props = {dims[0]: f"规格{i}"}
        try:
            price = round(float(s.get("price") or 0), 2)
        except (TypeError, ValueError):
            price = 0.0
        if price <= 0:
            continue
        skus.append({"sku_id": f"s_{pid}_{i}", "properties": props, "price": price})
    skus.sort(key=lambda s: s["price"])
    # 价格阶梯去重：同价则按 8% 递增拉开（金标准 720/980/1260 是阶梯价）
    for i in range(1, len(skus)):
        if skus[i]["price"] <= skus[i - 1]["price"]:
            skus[i]["price"] = round(skus[i - 1]["price"] * 1.08 + 1, 2)
    base_price = skus[0]["price"] if skus else round(float(gen.get("base_price") or 0), 2)

    return {
        "product_id": pid,
        "title": (gen.get("title") or "").strip(),
        "brand": brand,
        "category": orig["category"],
        "sub_category": orig["sub_category"],
        "base_price": base_price,
        "image_path": orig["image_path"],
        "skus": skus,
        "rag_knowledge": {
            "marketing_description": (gen.get("marketing_description") or "").strip(),
            "official_faq": [
                {"question": (f.get("question") or "").strip(),
                 "answer": (f.get("answer") or "").strip()}
                for f in (gen.get("official_faq") or [])
            ],
            "user_reviews": [
                {"nickname": (r.get("nickname") or "").strip(),
                 "rating": int(r.get("rating") or 5),
                 "content": (r.get("content") or "").strip()}
                for r in (gen.get("user_reviews") or [])
            ],
        },
    }


async def enrich_one(gw, path: Path, retries: int, dry_run: bool, sem) -> tuple[str, list[str]]:
    orig = json.loads(path.read_text(encoding="utf-8"))
    sub = orig["sub_category"]
    kb = SUB_KB.get(sub)
    if not kb:
        return path.name, [f"no_kb:{sub}"]

    # 品牌：原品牌在 KB 白名单则保留（保持数据稳定），否则按 pid 稳定改派
    brand = orig["brand"]
    if brand not in kb["brands"]:
        idx = int("".join(filter(str.isdigit, orig["product_id"])) or 0)
        brand = kb["brands"][idx % len(kb["brands"])]

    dims = kb["dims"] + ["规格"]
    lo, hi = kb["price"]
    prompt = PROMPT.format(category=orig["category"], sub_category=sub, brand=brand,
                           lo=lo, hi=hi, dims="、".join(kb["dims"]),
                           dim0=dims[0], dim1=dims[1])

    last_errs: list[str] = ["no_attempt"]
    async with sem:
        for attempt in range(retries + 1):
            try:
                raw = await asyncio.wait_for(gw.chat("content_generation", prompt), timeout=180)
            except Exception as e:  # noqa: BLE001
                last_errs = [f"llm_error:{type(e).__name__}"]
                continue
            gen = _parse_json(raw)
            if not gen:
                last_errs = ["json_unparseable"]
                continue
            merged = _merge(orig, gen, brand, dims)
            errs = [e for e in check_product(merged, path.name)
                    if not e.startswith("image_file_missing")]  # 图片单独补
            if not errs:
                if not dry_run:
                    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
                return path.name, []
            last_errs = errs
    return path.name, last_errs


async def main_async(args):
    from app.model_gateway.gateway import get_model_gateway

    gw = get_model_gateway()
    files: list[Path] = []
    for d in args.dirs:
        fs = sorted(glob.glob(str(BASE / d / "data" / "*.json")))
        if args.only_failing:
            keep = []
            for f in fs:
                p = json.loads(Path(f).read_text(encoding="utf-8"))
                errs = [e for e in check_product(p, f) if not e.startswith("image_file_missing")]
                if not errs:
                    continue
                # 保护金标准：只有结构类问题的商品不过 LLM（由 fix_structural.py 处理）
                if args.content_only and not has_content_error(errs):
                    continue
                keep.append(f)
            fs = keep
        if args.limit:
            fs = fs[:args.limit]
        files += [Path(f) for f in fs]

    print(f"待富化 {len(files)} 个商品（并发 {args.concurrency}，重试 {args.retries}）")
    sem = asyncio.Semaphore(args.concurrency)
    done = ok = 0
    failures: dict[str, list[str]] = {}
    tasks = [enrich_one(gw, f, args.retries, args.dry_run, sem) for f in files]
    for coro in asyncio.as_completed(tasks):
        name, errs = await coro
        done += 1
        if errs:
            failures[name] = errs
        else:
            ok += 1
        if done % 20 == 0 or done == len(files):
            print(f"  进度 {done}/{len(files)}  达标 {ok}  失败 {len(failures)}")

    print(f"\n=== 富化完成: {ok}/{len(files)} 达标 ===")
    if failures:
        print("失败样例:", dict(list(failures.items())[:8]))
    return 0 if ok == len(files) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dirs", nargs="+", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only-failing", action="store_true",
                    help="只处理当前未达标的商品（幂等增量修复）")
    ap.add_argument("--content-only", action="store_true",
                    help="仅当存在文案类违规时才调 LLM（保护人工精修的金标准商品）")
    args = ap.parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
