#!/usr/bin/env python
"""V1 Demo Pack 导出 — 从真实运行结果导出预设演示场景。

用法:
  python scripts/export_demo_pack.py --scenario bluetooth_headphones
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "backend"))

DEMO_SCENARIOS = {
    "bluetooth_headphones": {
        "name": "蓝牙耳机推荐",
        "description": "用户想买一款蓝牙耳机，豆仔通过意图识别→检索→评分→推荐完成导购",
        "query": "推荐一款降噪好的蓝牙耳机，预算500以内",
        "expected_category": "数码电子",
        "expected_sub_category": "真无线耳机",
        "mock_products": ["p_digital_007", "p_digital_009", "p_digital_011"],
    },
    "skincare_sunscreen": {
        "name": "防晒霜推荐",
        "description": "夏天到了，用户想买防晒霜，豆仔根据肤质和场景推荐",
        "query": "适合夏天用的防晒霜，不油腻",
        "expected_category": "美妆护肤",
        "mock_products": [],
    },
    "running_shoes": {
        "name": "跑步鞋推荐",
        "description": "用户想买跑步鞋，豆仔根据运动类型和预算推荐",
        "query": "跑步穿的透气运动鞋，预算300左右",
        "expected_category": "服饰运动",
        "mock_products": [],
    },
    "coffee_recommend": {
        "name": "咖啡推荐",
        "description": "用户想买咖啡豆，豆仔推荐食品饮料品类商品",
        "query": "推荐一款好喝的咖啡豆，不要太苦",
        "expected_category": "食品饮料",
        "mock_products": [],
    },
}


def main():
    parser = argparse.ArgumentParser(description="Demo Pack 导出工具")
    parser.add_argument("--scenario", type=str, default="", help="场景名")
    parser.add_argument("--list", action="store_true", help="列出所有场景")
    args = parser.parse_args()

    if args.list:
        print("可用 Demo 场景:")
        for sid, sc in DEMO_SCENARIOS.items():
            print(f"  {sid}: {sc['name']} — {sc['description']}")
        return

    out_dir = PROJECT_DIR / "data" / "demo_packs"
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.scenario:
        sc = DEMO_SCENARIOS.get(args.scenario)
        if not sc:
            print(f"未知场景: {args.scenario}")
            sys.exit(1)

        pack = {
            "scenario_id": args.scenario,
            **sc,
            "exported_at": None,
        }
        out_file = out_dir / f"{args.scenario}.json"
        out_file.write_text(json.dumps(pack, ensure_ascii=False, indent=2))
        print(f"Demo Pack 已导出: {out_file}")
    else:
        # 导出全部
        for sid, sc in DEMO_SCENARIOS.items():
            pack = {"scenario_id": sid, **sc, "exported_at": None}
            out_file = out_dir / f"{sid}.json"
            out_file.write_text(json.dumps(pack, ensure_ascii=False, indent=2))
            print(f"Demo Pack 已导出: {out_file}")

    print(f"\n共导出 {len(DEMO_SCENARIOS)} 个场景")


if __name__ == "__main__":
    main()
