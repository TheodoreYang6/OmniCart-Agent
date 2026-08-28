"""V1 Response Guard — 回答守门检查。

ResponseAgent 输出后执行，轻量规则不阻塞回答。
标记硬失败（幻觉/编造），写入 harness_report 供前端展示。
"""

import re
import logging
from app.schemas.workflow import WorkflowState

_log = logging.getLogger(__name__)


class ResponseGuard:
    """回答守门器 — 轻量规则检查 + 标记。"""

    # 品牌列表（幻觉检测用 — 对齐 ecommerce_agent_dataset 全部 65 个品牌）
    _KNOWN_BRANDS = [
        # 数码电子
        "Apple", "苹果", "华为", "HUAWEI", "小米", "Samsung", "三星",
        "Sony", "索尼", "Bose", "JBL", "Sennheiser", "AirPods",
        "Anker", "安克", "Baseus", "倍思", "漫步者", "Edifier",
        "QCY", "OPPO", "vivo", "联想", "Lenovo",
        # 服饰运动
        "Nike", "耐克", "Adidas", "阿迪达斯", "优衣库", "Uniqlo",
        "李宁", "安踏", "特步", "迪卡侬", "Decathlon",
        "The North Face", "北面", "始祖鸟", "Arc'teryx",
        "露露乐蒙", "Lululemon", "萨洛蒙", "Salomon",
        "HOKA", "Osprey", "迈乐", "Merrell",
        # 美妆护肤
        "雅诗兰黛", "兰蔻", "SK-II", "资生堂", "科颜氏", "巴黎欧莱雅", "理肤泉",
        "玉兰油", "The Ordinary", "珀莱雅", "薇诺娜",
        "AHC", "安热沙", "完美日记", "花西子", "方里", "芳珂", "珊珂",
        # 食品饮料
        "雀巢", "三顿半", "蒙牛", "伊利", "元气森林", "可口可乐",
        "农夫山泉", "东方树叶", "康师傅", "统一", "红牛", "东鹏",
        "三只松鼠", "良品铺子", "百草味", "日清", "海天", "李锦记",
        "纯甄", "金典",
    ]

    def check(self, state: WorkflowState) -> dict:
        answer = state.answer or ""
        products = state.retrieved_products or []
        context = state.context_prompt or ""
        user_query = state.user_query or ""

        report = {
            "evidence_bound": self._check_evidence(answer, products),
            "price_accurate": self._check_price(answer, products),
            "risk_warned": self._check_risk(answer, state.decision_results or []),
            "honest_on_empty": self._check_empty(answer, products),
            "hallucination": self._check_hallucination(answer, products, context, user_query),
            "cited_in_list": self._check_cited_in_list(answer, products,
                                                       state.answer_cited_pids or []),
            "group_coverage": self._check_group_coverage(state, products, answer),
            "health_claim_safe": self._check_health_claims(answer, products),
            "warnings": [],
        }

        # 汇总
        if not report["evidence_bound"]:
            report["warnings"].append("回答未引用证据（评价/FAQ等）")
        if not report["risk_warned"] and self._has_risks(state.decision_results or []):
            report["warnings"].append("存在风险项但回答未提醒")
        if not report["price_accurate"]:
            report["warnings"].append("价格引用不准确")
        if not report["cited_in_list"]:
            report["warnings"].append("回答未明确提及首选商品")
        if report["hallucination"]:
            report["warnings"].append(f"幻觉风险: {report['hallucination']}")
        if not report["group_coverage"]:
            report["warnings"].append("已命中的需求组未进入推荐交付")
        if not report["health_claim_safe"]:
            report["warnings"].append("健康/体重表述缺少商品事实支持")

        has_warnings = len(report["warnings"]) > 0
        hard_fail = (
            not report["honest_on_empty"]  # 无商品时编造推荐
            or bool(report["hallucination"])  # 提到了不存在的品牌
            or not report["cited_in_list"]  # 正文与锁定首选卡不一致
            or not report["price_accurate"]  # 提到商品却编造/遗漏价格
            or not report["group_coverage"]
            or not report["health_claim_safe"]
        )

        state.harness_report = {
            "schema_valid": True,
            "evidence_bound": report["evidence_bound"],
            "price_accurate": report["price_accurate"],
            "group_coverage": report["group_coverage"],
            "health_claim_safe": report["health_claim_safe"],
            "risk_warned": report["risk_warned"],
            "honest_on_empty": report["honest_on_empty"],
            "guard_warnings": report["warnings"],
            "passed": not hard_fail,
            "failure_source": None if not hard_fail else "response_guard",
        }

        if hard_fail:
            _log.warning(f"ResponseGuard FAILED: {report['warnings']}")

        return report

    # ---- 各项检查 ----

    def _check_cited_in_list(self, answer: str, products: list[dict],
                             cited_pids: list[str]) -> bool:
        """回答提到的商品必须在送给 LLM 的候选清单内（spec §3）。

        实现：取清单内商品（answer_cited_pids 对应，缺失时退回前 5），校验回答至少
        引用其中一款；并检查是否提到了清单外商品的品牌+商品名组合（跨清单引用）。
        空候选/空回答不算违规（由 honest_on_empty 管）。
        """
        if not answer or not products:
            return True
        pid_set = set(cited_pids) if cited_pids else {
            p.get("product_id", "") for p in products[:5]}
        in_list, out_list = [], []
        for p in products:
            (in_list if p.get("product_id", "") in pid_set else out_list).append(p)
        if not in_list:
            return True

        def _mentioned(prod: dict) -> bool:
            title = str(prod.get("title") or "")
            brand = str(prod.get("brand") or "")
            normalized_title = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", title.lower())
            normalized_answer = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", answer.lower())
            if normalized_title and len(normalized_title) >= 6 and normalized_title[:10] in normalized_answer:
                return True
            # 标准回答会把 100 字商品标题压缩为“品牌 + 型号”。品牌本身不能
            # 作为引用；至少还需一个型号/英文产品线词，避免仅说“小米”误判。
            model_words = re.findall(r"[A-Za-z]+[A-Za-z0-9-]*|\d+[A-Za-z-]*", title)
            return bool(
                brand and brand.lower() in answer.lower() and
                any(len(word) >= 3 and word.lower() in answer.lower() for word in model_words)
            )

        def _family_stub(prod: dict) -> str:
            title = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(prod.get("title") or "").lower())
            brand = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(prod.get("brand") or "").lower())
            if brand and title.startswith(brand):
                title = title[len(brand):]
            return f"{brand}:{title[:18]}"

        if not any(_mentioned(p) for p in in_list):
            return False
        # 清单外商品被引用 → 答文与列表错位
        # 同系列不同规格可能共用“品牌 + 型号”称呼。回答只要明确首选
        # 即可，不把这种无法通过短称区分的变体误判成引用了备选。
        in_stubs = {_family_stub(product) for product in in_list}
        distinct_out_list = [product for product in out_list if _family_stub(product) not in in_stubs]
        return not any(_mentioned(product) for product in distinct_out_list)

    def _check_evidence(self, answer: str, products: list[dict]) -> bool:
        """证据绑定：回答是否引用了具体商品信息（品牌名/标题关键词/证据内容）。"""
        if not products:
            return True
        for p in products[:3]:
            brand = p.get("brand", "")
            title = p.get("title", "")
            # 品牌名命中
            if brand and len(brand) >= 2 and brand in answer:
                return True
            # 标题滑窗：中英文都支持
            for window in [4, 3]:
                for i in range(len(title) - window + 1):
                    sub = title[i:i+window].strip()
                    if len(sub) >= 2 and sub in answer:
                        return True
            # 英文品牌/型号关键词
            eng_words = re.findall(r'[A-Za-z0-9][A-Za-z0-9\- ]{1,}[A-Za-z0-9]', title)
            for w in eng_words[:3]:
                if len(w) >= 3 and w.lower() in answer.lower():
                    return True
        return False

    def _check_price(self, answer: str, products: list[dict]) -> bool:
        """价格准确：如果提到了商品名，价格是否正确。"""
        # 最终交付最多有三张首选卡。旧实现只校验前两张，第三张即使被模型
        # 说错价格也能通过 Guard，导致卡片与正文再次失去同一口径。
        for p in products[:3]:
            brand = p.get("brand", "")
            title = p.get("title", "")
            price = int(p.get("price", 0))
            # 不能用 ``str(price) in answer``：型号 C300、容量 300ml、续航
            # 300 小时都会被错误当成金额。只接受货币符号或明确价格单位。
            price_patterns = (
                rf"[¥￥]\s*{price}(?:\.0+)?(?!\d)",
                rf"(?<![A-Za-z0-9]){price}(?:\.0+)?\s*(?:元|块)(?![A-Za-z0-9])",
            )
            # 检查回答是否引用了该商品（品牌或标题关键词）
            mentioned = (brand and len(brand) >= 2 and brand in answer)
            if not mentioned:
                # 标题滑窗：4字片段命中即认为引用了该商品
                for i in range(len(title) - 3):
                    if title[i:i+4] in answer:
                        mentioned = True
                        break
            if mentioned and price > 0:
                if not any(re.search(pattern, answer) for pattern in price_patterns):
                    return False
        return True

    def _check_risk(self, answer: str, decisions: list[dict]) -> bool:
        """风险覆盖：有风险标签时，回答是否提及。"""
        all_risks = set()
        for d in decisions[:3]:
            for r in d.get("risk_factors", []):
                r_str = str(r)
                # 提取关键词（中英文）
                keywords = re.findall(r'[一-鿿A-Za-z0-9]{2,4}', r_str)
                all_risks.update(keywords)
                # 也加入完整风险文本的前6字
                if len(r_str) >= 2:
                    all_risks.add(r_str[:6])
        if not all_risks:
            return True
        return any(kw in answer for kw in all_risks if len(kw) >= 2)

    def _check_empty(self, answer: str, products: list[dict]) -> bool:
        """空结果诚实：无商品时不应推荐具体品牌/型号。"""
        if products:
            return True
        misleading = ["推荐", "值得买", "建议入手", "可以考虑", "这款", "那个",
                      "Anker", "Baseus", "倍思", "紫米", "绿联"]
        return not any(kw in answer for kw in misleading)

    def _check_hallucination(
        self, answer: str, products: list[dict], context: str, user_query: str
    ) -> str:
        """幻觉检测：回答是否引用了不在检索结果中的品牌。

        排除: 用户自己提到的品牌 / 否定/解释性语境中的品牌引用。
        """
        if not products:
            return ""
        from app.decision.rules import BRAND_ALIASES
        product_brands = set(p.get("brand", "").lower() for p in products)
        aliased = set(product_brands)
        for b in product_brands:
            alias = BRAND_ALIASES.get(b)
            if alias:
                aliased.add(alias)

        NEGATION_WORDS = ["非", "不符合", "不是", "并非", "除外", "排除",
                          "暂无", "没有该", "没有这个", "无此", "不属于"]

        for brand in self._KNOWN_BRANDS:
            if brand.lower() in answer.lower() and brand.lower() not in aliased:
                # 用户自己提到过（含别名）→ 不算幻觉
                user_mentioned = brand.lower() in user_query.lower()
                if not user_mentioned:
                    alias = BRAND_ALIASES.get(brand.lower(), "")
                    user_mentioned = alias in user_query.lower()
                if not user_mentioned:
                    user_mentioned = brand.lower() in context.lower()
                if not user_mentioned:
                    alias = BRAND_ALIASES.get(brand.lower(), "")
                    user_mentioned = alias in context.lower()
                if user_mentioned:
                    continue  # 用户提过的品牌，跳过
                # 否定/解释性语境（如 "Nike长裤为下装，非T恤"）→ 也不算幻觉
                idx = answer.lower().find(brand.lower())
                if idx >= 0:
                    ctx_win = answer[max(0, idx-10):idx+len(brand)+20]
                    if any(nw in ctx_win for nw in NEGATION_WORDS):
                        continue
                return f"提到了非检索结果的品牌 '{brand}'"
        return ""

    @staticmethod
    def _check_group_coverage(state: WorkflowState, products: list[dict], answer: str) -> bool:
        """Every matched compound group needs a card *and* answer coverage."""
        groups = getattr(state, "retrieval_groups", []) or []
        # 单一检索组已经由 cited_in_list 校验；把它当“多目标覆盖”会要求回答
        # 再次精确复述完整长标题，造成明明有首选卡却被误判 Guard 失败。
        if len(groups) < 2:
            return True
        delivered = set((state.primary_product_ids or []) + (state.alternative_product_ids or []))
        products_by_id = {str(p.get("product_id")): p for p in products if p.get("product_id")}
        lowered_answer = (answer or "").lower()
        for group in groups:
            status = group.get("status", "") if isinstance(group, dict) else getattr(group, "status", "")
            pids = group.get("product_ids", []) if isinstance(group, dict) else getattr(group, "product_ids", [])
            matched = set(pids) & delivered
            if status == "matched" and pids:
                if not matched:
                    return False
                # The user must also be told about every delivered group rather
                # than receiving an apparently complete answer about only one.
                displayed = products_by_id.get(str(next(iter(matched))), {})
                title = str(displayed.get("title", "")).lower()
                brand = str(displayed.get("brand", "")).lower()
                if title and title not in lowered_answer and brand and brand not in lowered_answer:
                    return False
        return True

    @staticmethod
    def _check_health_claims(answer: str, products: list[dict]) -> bool:
        """Weight outcomes are never product claims; dietary language needs facts."""
        lowered = answer.lower()
        if any(term in lowered for term in ("不长胖", "不会胖", "减肥效果", "保证瘦", "瘦下来", "燃脂")):
            return False
        fact_keys = {
            f.get("fact_key", "")
            for product in products
            for f in (product.get("product_facts", []) or [])
        }
        assertions = {
            "0糖": "nutrition.zero_sugar", "无糖": "nutrition.zero_sugar",
            "低糖": "nutrition.low_sugar", "0脂": "nutrition.zero_fat",
            "低脂": "nutrition.low_fat", "低卡": "nutrition.low_calorie",
            "0卡": "nutrition.zero_calorie", "高蛋白": "nutrition.high_protein",
        }
        return all(key in fact_keys for phrase, key in assertions.items() if phrase in answer)

    def _has_risks(self, decisions: list[dict]) -> bool:
        return any(d.get("risk_factors") for d in decisions)
