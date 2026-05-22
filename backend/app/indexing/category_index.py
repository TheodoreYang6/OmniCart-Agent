"""V1 Hierarchical Shopping Knowledge Index — 分层品类知识索引。

将扁平的商品数据组织为层级结构：
  Level 0: 四大品类 (美妆护肤/数码电子/服饰运动/食品饮料)
  Level 1: 子品类
  Level 2: 品牌
  Level 3: 具体商品

用于快速导航、品类筛选、和相关推荐。
"""

from typing import Optional
from collections import defaultdict


class CategoryIndex:
    """分层品类索引 — V1 内存实现。"""

    def __init__(self):
        # 四级索引: category → sub_category → brand → [product_ids]
        self._tree: dict[str, dict] = {}
        # 关键词 → category 映射（快速品类识别）
        self._keyword_map: dict[str, str] = {}

    def build(self, products: list[dict]):
        """从商品列表构建分层索引。"""
        self._tree.clear()
        for p in products:
            cat = p.get("category", "其他")
            sub = p.get("sub_category", "通用")
            brand = p.get("brand", "未知品牌")
            pid = p.get("product_id", "")

            if cat not in self._tree:
                self._tree[cat] = {"_subs": {}, "_count": 0}
            self._tree[cat]["_count"] += 1

            subs = self._tree[cat]["_subs"]
            if sub not in subs:
                subs[sub] = {"_brands": {}, "_count": 0}
            subs[sub]["_count"] += 1

            brands = subs[sub]["_brands"]
            if brand not in brands:
                brands[brand] = []
            brands[brand].append(pid)

    def add_keywords(self, keyword_map: dict[str, str]):
        """注册关键词→品类映射（用于意图识别）。"""
        self._keyword_map.update(keyword_map)

    def get_category(self, keyword: str) -> Optional[str]:
        """通过关键词查找品类。"""
        return self._keyword_map.get(keyword)

    def get_sub_categories(self, category: str) -> list[str]:
        """获取某品类下的所有子品类。"""
        cat = self._tree.get(category, {})
        subs = cat.get("_subs", {})
        return sorted(subs.keys())

    def get_brands(self, category: str, sub_category: str = "") -> list[str]:
        """获取品类/子品类下的所有品牌。"""
        cat = self._tree.get(category, {})
        if not cat:
            return []
        subs = cat.get("_subs", {})
        if sub_category:
            target = subs.get(sub_category, {})
            return sorted(target.get("_brands", {}).keys())
        all_brands = set()
        for s in subs.values():
            all_brands.update(s.get("_brands", {}).keys())
        return sorted(all_brands)

    def get_products(self, category: str = "", sub_category: str = "", brand: str = "") -> list[str]:
        """按层级筛选商品 ID。"""
        if not category:
            all_pids = []
            for cat in self._tree:
                all_pids.extend(self.get_products(cat, sub_category, brand))
            return all_pids

        cat_data = self._tree.get(category, {})
        subs = cat_data.get("_subs", {})

        if sub_category:
            target = subs.get(sub_category, {})
            brands = target.get("_brands", {})
            if brand:
                return brands.get(brand, [])
            return [pid for pids in brands.values() for pid in pids]

        all_pids = []
        for s in subs.values():
            for pids in s.get("_brands", {}).values():
                all_pids.extend(pids)
        return all_pids

    def summary(self) -> dict:
        return {
            "categories": len(self._tree),
            "keywords": len(self._keyword_map),
            "hierarchy": {
                cat: {
                    "count": data["_count"],
                    "sub_categories": {
                        sub: {"count": sdata["_count"], "brands": len(sdata.get("_brands", {}))}
                        for sub, sdata in data.get("_subs", {}).items()
                    }
                }
                for cat, data in self._tree.items()
            },
        }
