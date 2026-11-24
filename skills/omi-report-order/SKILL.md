---
name: omi-report-order
description: Discover and purchase a catalog-backed OmniCart shopping report for a chosen product category and budget. Use when a user asks an Agent to obtain a paid Omi report and explicitly chooses Alipay. Returns the verified receipt and report after payment.
---

# 欧米选购报告下单

1. 用 `python3 scripts/report_order.py service` 查询服务、价格和环境，用 `categories` 获取品类。路径以本 Skill 目录为基准。已部署的商家入口由用户或运行环境通过 `OMNICART_REPORT_BASE_URL` 指定。
2. 收集商品品类和商品预算，将预算转为人民币分。询问用户是否要生成该服务报价。下单前使用所属账号的会话，由用户通过环境变量 `OMNICART_REPORT_SESSION_TOKEN` 提供现有 OmniCart Bearer token。交互中不索取或输出 token、支付宝密码或私钥。
3. 用 `quote "真无线耳机" 50000` 获取报价。展示服务名称、品类、商品预算、报告服务费和支付环境。等待用户明确同意通过支付宝支付这笔服务费。
4. 生产环境中，从官方 `alipay-payment-skill` 获取当前会话 ID，运行 `confirm <order_id> --session-id <sessionId> --framework <宿主>`。脚本用官方 CLI 转换收银台链接。将输出的 `paymentLink` 原样交给支付技能，使用同一会话。按官方技能指引展示确认步骤并沿同一入口查询，处理中等待用户完成付款。遇到超时先查原订单。
5. 用 `refresh <order_id>` 请求商户服务端查单。只在 `status` 为 `paid` 且包含 `report` 时，交付报告和商户查单验证过的交易号。其余状态下说明订单结果，保留订单号用于继续查单。

`demo` 和 `sandbox` 环境运行 `confirm <order_id>`。请用户在浏览器的报告页完成本地演示，或用支付宝沙箱买家完成沙箱付款。正式支付宝钱包仅接收生产收银台材料。

官方支付处理技能由运行环境或用户安装。使用 [支付宝支付处理技能](https://github.com/alipay/payment-skills/tree/main/alipay-payment-skill) 中的收银台流程。
