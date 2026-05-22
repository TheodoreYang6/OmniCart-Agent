"""V1 Visual Evidence Grounding — 字段级视觉证据绑定。

将 Visual Agent 提取的字段映射到具体证据引用，
实现"这个参数是从截图的哪个位置提取的"可追溯。
"""


class VisualGrounding:
    """视觉证据绑定器 — V1 基础实现。"""

    def ground(self, visual_result: dict, product_id: str) -> list[dict]:
        """将 VisualResult 字段绑定为结构化 grounding 记录。"""
        grounded = []
        field_mapping = {
            "product_name": "商品名称",
            "brand": "品牌",
            "category": "品类",
            "specs": "规格参数",
            "price_estimate": "预估价格",
        }

        for field, label in field_mapping.items():
            if field == "specs" and isinstance(visual_result.get("specs"), dict):
                for spec_key, spec_val in visual_result["specs"].items():
                    grounded.append({
                        "field": f"specs.{spec_key}",
                        "label": f"规格:{spec_key}",
                        "value": str(spec_val),
                        "source": "visual_agent",
                        "product_id": product_id,
                        "confidence": visual_result.get("confidence", 0.5),
                        "evidence_id": f"V-{product_id}-specs-{spec_key}",
                    })
            else:
                value = visual_result.get(field)
                if value:
                    grounded.append({
                        "field": field,
                        "label": label,
                        "value": str(value),
                        "source": "visual_agent",
                        "product_id": product_id,
                        "confidence": visual_result.get("confidence", 0.5),
                        "evidence_id": f"V-{product_id}-{field}",
                    })

        return grounded

    def ground_all(self, visual_result: dict, retrieved_products: list[dict]) -> list[dict]:
        """对检索到的所有商品做 visual grounding。"""
        all_grounded = []
        for p in retrieved_products:
            pid = p.get("product_id", "")
            all_grounded.extend(self.ground(visual_result, pid))
        return all_grounded
