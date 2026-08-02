"""Service 层 Prompt 模板 — 对话摘要 / 偏好解析 / 关键词改写。

模板常量集中定义，业务代码通过 build_xxx() 组装函数引用。
"""

from __future__ import annotations

# ============================================================
# ContextCompressor — 对话历史增量摘要
# ============================================================

COMPRESSION_SYSTEM = (
    "你是购物对话摘要器。将对话历史压缩为 ≤120 字的要点摘要。\n\n"
    "规则：\n"
    "1. 只保留事实：用户需求、约束、偏好、已推荐商品、风险提示、态度反馈\n"
    "2. 不编造、不推测、不评价用户的选择\n"
    "3. 如果用户表达了对推荐的态度（喜欢/不喜欢/太贵/不合适），必须记录\n"
    "4. 如果有欧米提出但用户尚未回答的问题，记录为 open_question\n"
    "5. 输出 JSON 格式，不要其他内容\n\n"
    '格式: {"summary": "摘要", "open_question": "未回答问题"|null}'
)

COMPRESSION_USER = (
    "历史摘要: {prev_summary}\n"
    "本轮用户: {last_query}\n"
    "欧米回复: {last_answer}\n"
    "待回答: {pending_question}\n\n"
    "请更新摘要 JSON:"
)


def get_compression_system() -> str:
    """获取对话摘要 system prompt。"""
    return COMPRESSION_SYSTEM


def build_compression_user(
    prev_summary: str,
    last_query: str,
    last_answer: str,
    pending_question: str,
) -> str:
    """渲染对话摘要 user prompt。"""
    return COMPRESSION_USER.format(
        prev_summary=prev_summary,
        last_query=last_query,
        last_answer=last_answer,
        pending_question=pending_question,
    )


# ============================================================
# UserProfileService — 购物偏好解析
# ============================================================

PROFILE_PARSE_SYSTEM = (
    "你是一个购物偏好解析器。从用户输入中提取网购偏好，输出 JSON。\n\n"
    "规则：\n"
    "1. 只提取明确提到的内容，绝对不推测\n"
    "2. categories 字段填写大类（数码电子/美妆护肤/服饰运动/食品饮料/家居用品/母婴用品/运动户外/个护清洁）\n"
    "3. sub_categories 填写小类（手机/电脑/耳机/护肤品/面膜/洗发水/保温杯/纸尿裤/帐篷...）\n"
    "4. 肤质/发质放入 skin_type 或 hair_type\n"
    "5. '不喜欢/讨厌/怕/别给我'后面的内容放入 avoid_tags\n"
    "6. '喜欢/偏好/想要/必须'后面的特性放入 must_tags\n"
    "7. 空值用 [] 或 null，只输出 JSON\n\n"
    "示例：\n"
    "- '喜欢苹果手机预算500' → {categories:['数码电子'],sub_categories:['手机'],brands:['Apple'],devices:['iPhone'],budget_max:500}\n"
    "- '我是油皮敏感肌，喜欢资生堂'\n"
    "  → {skin_type:['油皮','敏感肌'],brands:['资生堂'],categories:['美妆护肤'],sub_categories:['护肤品']}\n"
    "- '经常出差要便携，不喜欢太重，要支持快充'\n"
    "  → {scenarios:['出差'],avoid_tags:['太重'],must_tags:['快充']}"
)


def get_profile_parse_system() -> str:
    """获取偏好解析 system prompt。"""
    return PROFILE_PARSE_SYSTEM


def build_profile_parse_user(raw_text: str) -> str:
    """渲染偏好解析 user prompt。"""
    return f"用户输入: {raw_text}\n\nJSON:"


# ============================================================
# KeywordRewriter — 口语查询 → 搜索关键词
# ============================================================

KEYWORD_EXTRACT_PROMPT = (
    "你是一个搜索关键词提取器。将用户的购物口语转化为商品搜索引擎友好的关键词，"
    "用空格分隔。提取品类、品牌、属性、场景等核心词。最多输出10个词。\n\n"
    "{ctx_part}"
    "用户说：{user_query}\n关键词："
)


def build_keyword_extract_prompt(user_query: str, context: str = "") -> str:
    """渲染关键词提取 prompt。context 非空时注入上文段。"""
    ctx_part = f"上文：{context}\n" if context else ""
    return KEYWORD_EXTRACT_PROMPT.format(ctx_part=ctx_part, user_query=user_query)
