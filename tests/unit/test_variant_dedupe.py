"""同款变体去重单测（spec: 混合检索与四bug根治 §2）。

数据集存在 81 组归一标题近重复（同款不同 product_id），按 pid 去重无感
→ 用户看到"同一产品的不同页面"。本测锁住折叠行为。
"""

from types import SimpleNamespace

from app.retrieval.semantic_retriever import SemanticRetriever


class _FakeRepo:
    def __init__(self, products: dict):
        self._p = products

    def get_by_id(self, pid: str):
        return self._p.get(pid)


def _prod(pid, title, brand="探路者", sub="登山鞋"):
    return SimpleNamespace(product_id=pid, title=title, brand=brand, sub_category=sub)


def test_variant_key_folds_same_model_different_spec():
    """同款不同规格/型号后缀 → 同一 key。"""
    r = SemanticRetriever(_FakeRepo({}))
    k1 = r._variant_key(_prod("a", "探路者TERRA系列GORE-TEX防水登山鞋男款防滑耐磨高帮42码"))
    k2 = r._variant_key(_prod("b", "探路者TERRA系列GORE-TEX防水登山鞋男款防滑耐磨高帮43码"))
    assert k1 == k2, (k1, k2)


def test_variant_key_keeps_different_products_apart():
    """不同款（主体词不同）不得误折叠。"""
    r = SemanticRetriever(_FakeRepo({}))
    k1 = r._variant_key(_prod("a", "探路者TERRA系列防水登山鞋男款"))
    k2 = r._variant_key(_prod("b", "探路者速干短袖T恤男款"))
    assert k1 != k2


def test_variant_key_brand_and_subcategory_matter():
    """同标题但不同品牌/子品类 → 不同款。"""
    r = SemanticRetriever(_FakeRepo({}))
    base = "轻量防水登山鞋"
    assert r._variant_key(_prod("a", base, brand="探路者")) != r._variant_key(
        _prod("b", base, brand="迪卡侬"))
    assert r._variant_key(_prod("a", base, sub="登山鞋")) != r._variant_key(
        _prod("b", base, sub="徒步鞋"))


def test_dedupe_variants_keeps_best_and_records_count():
    """三条真近重复（数据集实例）→ 只返回 1 条最高分，另 2 条记入 variant_map。"""
    products = {
        "p1": _prod("p1", "威尔胜Wilson NBA官方比赛用球真皮版7号篮球",
                    brand="威尔胜", sub="篮球"),
        "p2": _prod("p2", "威尔胜Wilson NBA 官方比赛用球真皮版7号篮球",
                    brand="威尔胜", sub="篮球"),
        "p3": _prod("p3", "威尔胜Wilson NBA官方比赛用球真皮版7号篮球 专业室内",
                    brand="威尔胜", sub="篮球"),
    }
    r = SemanticRetriever(_FakeRepo(products))
    kept = r._dedupe_variants([("p1", 0.9), ("p3", 0.8), ("p2", 0.7)], top_k=5)
    kept_ids = [pid for pid, _ in kept]
    assert kept_ids == ["p1"], f"三条同款应只留最高分一条: {kept_ids}"
    assert sorted(r._variant_map.get("p1", [])) == ["p2", "p3"], r._variant_map


def test_dedupe_fills_up_to_top_k_after_folding():
    """折叠后仍应凑满 top_k（先多取候选再折叠，不能因去重而少给）。"""
    products = {}
    ranked = []
    # 3 组同款各 2 条 → 折叠后应剩 3 条
    for g in range(3):
        for v in range(2):
            pid = f"g{g}v{v}"
            products[pid] = _prod(pid, f"品牌{g}专业登山杖碳纤维{v}节", brand=f"品牌{g}", sub="登山杖")
            ranked.append((pid, 1.0 - g * 0.1 - v * 0.01))
    r = SemanticRetriever(_FakeRepo(products))
    kept = r._dedupe_variants(ranked, top_k=3)
    assert len(kept) == 3, kept
    assert len({r._variant_key(products[pid]) for pid, _ in kept}) == 3


def test_dedupe_without_repo_degrades_to_truncate():
    """无 repo 时降级为普通截断，不得抛异常。"""
    r = SemanticRetriever(None)
    kept = r._dedupe_variants([("a", 1.0), ("b", 0.9), ("c", 0.8)], top_k=2)
    assert kept == [("a", 1.0), ("b", 0.9)]
