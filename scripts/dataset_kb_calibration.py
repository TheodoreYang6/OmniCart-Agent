"""知识库校准补丁 —— 以人工精修金标准段（前四类 001-025，共 100 个商品）为地面真值。

来源说明：这 100 个商品的 (子品类, 品牌, 价格) 组合是人工核对过的真实在售数据，
因此把其中知识库未覆盖的品牌（多为同品牌的中英文别名，如 Apple 苹果 / 耐克 /
露露乐蒙 / 玉兰油 / 金典 / 纯甄）并入白名单，并按真实低价位放宽价格下界
（如单支入门精华 59 元、瓶装饮料 4 元），避免把真实数据误判为违规。
"""

from __future__ import annotations

# 子品类 -> 需补入白名单的真实品牌（金标准段实际在用）
EXTRA_BRANDS: dict[str, list[str]] = {
    "功能饮料": ["东鹏", "尖叫"],
    "卸妆": ["芳珂"],
    "帽子": ["北面"],
    "平板电脑": ["Apple 苹果", "vivo"],
    "徒步鞋": ["萨洛蒙", "迈乐"],
    "户外裤": ["始祖鸟"],
    "方便食品": ["日清"],
    "智能手机": ["Apple 苹果"],
    "洁面": ["珊珂"],
    "牛奶": ["金典"],
    "瑜伽裤": ["露露乐蒙"],
    "真无线耳机": ["Apple 苹果"],
    "眼霜": ["AHC"],
    "短袖T恤": ["耐克"],
    "笔记本电脑": ["Apple 苹果"],
    "篮球鞋": ["耐克"],
    "精华": ["The Ordinary"],
    "背包": ["Osprey", "The North Face"],
    "蜜粉": ["方里"],
    "跑步鞋": ["HOKA", "耐克"],
    "运动短裤": ["优衣库"],
    "速干T恤": ["耐克"],
    "酸奶": ["纯甄"],
    "防晒": ["巴黎欧莱雅"],
    "面霜": ["玉兰油", "理肤泉"],
}

# 子品类 -> 价格下界放宽值（真实入门价位）
PRICE_FLOOR: dict[str, float] = {
    "精华": 49.0,
    "茶饮": 3.0,
    "碳酸饮料": 3.0,
    "功能饮料": 4.0,
}


def apply(sub_kb: dict) -> None:
    """就地把校准补丁合并进 SUB_KB。"""
    for sub, brands in EXTRA_BRANDS.items():
        entry = sub_kb.get(sub)
        if not entry:
            continue
        for b in brands:
            if b not in entry["brands"]:
                entry["brands"].append(b)
    for sub, floor in PRICE_FLOOR.items():
        entry = sub_kb.get(sub)
        if entry:
            lo, hi = entry["price"]
            entry["price"] = (min(lo, floor), hi)
