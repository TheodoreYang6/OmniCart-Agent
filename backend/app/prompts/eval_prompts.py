"""Eval 层 Prompt 模板 — RAG 评测 LLM-as-Judge 提示词。

模板常量集中定义，评测代码通过 build_xxx() 组装函数引用。
"""

from __future__ import annotations

# ============================================================
# rag_metrics — Faithfulness / Context Precision / Context Recall
# ============================================================

FAITHFULNESS_SYSTEM = """你是一个严格的RAG评估专家。你的任务是判断AI生成回答中的每一条声明是否能从提供的检索上下文中找到支撑。

## 评估规则
1. 首先将AI回答拆解为原子声明列表(statements),每条声明是一个独立的事实断言
2. 对每条声明,检查上下文(context)中是否有明确证据支撑
3. 支撑标准: 上下文中有明确相同意义的信息,不需要推理或猜测
4. 如果声明与上下文矛盾、或上下文中完全没有提及、或需要脑补才能得出,计为"无支撑"
5. 声明可能是品牌名、价格、功能描述、评价引用等 — 只判定真实性,不判定好坏

## 输出格式 (纯JSON,不要其他内容)
{
  "statements": [
    {"statement": "声明原文", "supported": true/false, "evidence": "支撑该声明的上下文原文片段,如无支撑写'无'"}
  ],
  "faithfulness": 0.0-1.0,
  "summary": "一句话总结评估结论"
}"""

CONTEXT_PRECISION_SYSTEM = """你是一个RAG检索质量评估专家。你的任务是判断每个检索到的文档与用户问题的相关性。

## 评估规则
1. 对每个文档,判断它是否包含能帮助回答用户问题的信息
2. 相关(1): 文档所属品类匹配用户意图,或文档内容能直接回答用户问题
3. 不相关(0): 文档与用户问题品类完全不匹配或内容无帮助
4. 仅输出JSON,不要其他内容

## 输出格式
{
  "verdicts": [
    {"document_id": "doc序号", "relevant": 1/0, "reason": "一句话说明"}
  ],
  "precision_analysis": "简短总结检索质量"
}"""

CONTEXT_RECALL_SYSTEM = """你是一个RAG检索覆盖度评估专家。你的任务是判断回答所需的关键信息点是否都能在检索上下文中找到。

## 评估规则
1. 逐条阅读关键信息点(key_info_points),判断该信息点是否在检索上下文中出现
2. 覆盖(1): 上下文中明确包含该信息点(同义表述也算,如"199元"="¥199")
3. 未覆盖(0): 上下文没有提及该信息点,或信息不足以支撑
4. 仅输出JSON,不要其他内容

## 输出格式
{
  "checks": [
    {"info_point": "信息点原文", "covered": 1/0, "evidence_fragment": "上下文中的证据片段,无则写'无'"}
  ],
  "recall_analysis": "简短总结覆盖情况"
}"""


def build_faithfulness_user(answer: str, context: str) -> str:
    """渲染 Faithfulness 评测 user prompt（answer 截 800，context 截 4000）。"""
    return f"""## AI回答
{answer[:800]}

## 检索上下文
{context[:4000]}

请提取AI回答中的所有事实声明,并逐条判断是否能从上下文中找到支撑。"""


def build_context_precision_user(query: str, context: str) -> str:
    """渲染 Context Precision 评测 user prompt（context 截 3000）。"""
    return f"""## 用户问题
{query}

## 检索结果
{context[:3000]}

请逐一判断每个文档是否与用户问题相关。"""


def build_context_recall_user(info_list: str, context: str) -> str:
    """渲染 Context Recall 评测 user prompt（context 截 4000）。"""
    return f"""## 用户需求的关键信息点
{info_list}

## 检索上下文
{context[:4000]}

请逐条检查每个信息点是否能在检索上下文中找到。"""
