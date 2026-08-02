# Spec · 商品数据集金标准提质（归档摘要）

> 原始任务无独立 plan 文档（对话式推进），此为归档摘要。完整过程见 docs/工作日志.md 工作块 19。

## 目标
ecommerce_agent_dataset 全量 1000 商品达到金标准 p_beauty_001.json 质量：后四类
（家居/母婴/运动户外/个护清洁）信息与图片补全，前四类同步提质。

## 验收（终态 2026-07 达成）
- scripts/validate_dataset.py 20 项规则 1000/1000 通过（初始 2%）
- 892 缺图归零（ImageGen 子品类代表图 + 分发）
- PG 1000 件重灌、Qdrant 重建、API/前端/RAG 全链验证

## 关键资产
- scripts/{validate_dataset, enrich_dataset, dataset_kb, fix_structural, apply_subcategory_images}.py
- 金标准量尺：营销≥150字含品牌 / FAQ≥3条答案≥80字 / 评价≥5条评分分化 / SKU阶梯价 /
  base_price=最低SKU价 / 品牌-品类相符 / 模板套话黑名单 / SKU key 中文
