---
name: omi-report-order
description: Generate and retrieve a free OmniCart shopping report for a category and product budget. Returns catalog reference prices, FAQs and review samples.
---

# 欧米选购报告

1. 在技能目录运行 `python3 scripts/report_order.py service` 检查可用性，运行 `python3 scripts/report_order.py categories` 获取品类。通过 `OMNICART_REPORT_BASE_URL` 指定欧米服务地址。
2. 收集用户选择的品类和商品预算，将预算转为人民币分。运行环境通过 `OMNICART_REPORT_SESSION_TOKEN` 提供用户已有的 OmniCart 会话。
3. 运行 `python3 scripts/report_order.py generate "真无线耳机" 50000`。生成免费，接口直接返回 `report` 和报告编号 `order_id`。
4. 展示报告中的候选商品、参考价格、常见问答和评价样本。需要重新读取时，运行 `python3 scripts/report_order.py status <order_id>`。
