"""序号/数量解析 —— 抽取自 agent_stream 的 ``_parse_ordinal`` / ``_parse_qty``。

供购物车工具与 RuleToolRouter 复用，逻辑与旧实现逐字等价（保证 A/B 对拍）。
"""

from __future__ import annotations

import re

__all__ = ["CHINESE_NUM", "OrdinalResolver"]

CHINESE_NUM = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


class OrdinalResolver:
    """从中文/数字表达中解析序号与数量。"""

    @staticmethod
    def parse_ordinal(text: str, prefix: str) -> int | None:
        """从 '删除第二个' 提取序号 → 2（1-indexed）。支持 第X / X个 / 中文数字。"""
        m = re.search(r"(?:" + prefix + r")\s*(\d+|[一二三四五六七八九十]+)", text)
        if not m:
            m = re.search(r"(\d+)\s*个", text)
            if not m:
                m = re.search(r"([一二三四五六七八九十])\s*个", text)
        if not m:
            return None
        num_str = m.group(1)
        if num_str is None:
            return None
        if num_str.isdigit():
            return int(num_str)
        return CHINESE_NUM.get(num_str)

    @staticmethod
    def parse_qty(text: str) -> int | None:
        """从 '数量改成3' 提取数字。"""
        m = re.search(r"(\d+)", text)
        return int(m.group(1)) if m else None
