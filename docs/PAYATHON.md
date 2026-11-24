# 欧米选购报告与支付宝接入

欧米在 Web 和聊天中提供一次性付费的选购报告。买家选择品类和商品预算，确认服务费，付款后可在报告订单中查看商品对比、FAQ、评价样本和交易号。报告采用报价时的商品资料。支付宝订单在通知或主动查单通过验签并匹配订单后交付。实现见 [支付 API](../backend/app/api/report_payments.py) 和 [报告生成](../backend/app/services/shopping_report.py)。

| 入口 | 交付内容 | 平台接入 |
| --- | --- | --- |
| Web 选购报告 | 可重复查看的单次报告 | Vibe Pay 电脑网站支付 |
| 欧米到手价比较 | 可在 Agent 中运行的成本对照技能 | Skill Pay 一次性付费，提交技能包后由平台审核并交付 |
| 欧米选购报告下单 Skill | 发现报告服务、确认报价、委托付款、取回报告和交易号 | 支付宝支付处理技能的收银台流程 |

## 本地演示

准备有商品数据的 PostgreSQL。已有 OmniCart 数据栈可继续使用。安装本次新增的 Python 依赖，并从项目根目录运行迁移。

```bash
python -m pip install -r requirements.txt
alembic upgrade head
```

在本机 `.env` 设置 `OMNICART_REPORT_PAYMENT_MODE=demo`。用回环地址启动后端和 Web。打开 [选购报告](http://127.0.0.1:5173/reports)，登录后选择“真无线耳机”和商品预算 ¥500。依次点击“获取报价”“确认演示订单”“模拟付款成功”。报告显示服务交易号和候选商品。重新打开该订单可以查看已交付报告。

对话发起的演示从“我想看看选购报告”开始。点击欧米回复中的“查看选购报告”进入报价页，此后走同一结算流程。报告页会标记 Agent 发起的订单。

本地演示订单标记为 `demo`，无法触发支付宝付款或履约正式订单。仓库默认关闭报告收款。配置项见 [环境变量样例](../.env.example)。

## 购物车与对话支付

登录后保存收货地址，在 [购物车](http://127.0.0.1:5173/cart) 勾选商品并点击“支付宝结算”。核对商品、收货地址和金额，再确认支付。演示环境可点击“模拟付款成功”。付款确认后，订单进入“我的订单”，购物车会移除已付款且未变更的商品行。

在 [欧米对话](http://127.0.0.1:5173/chat) 发送“用支付宝结算购物车”，欧米调用 `order.cart_payment_quote` 并展示报价。在同一会话发送“确认支付”，欧米调用 `order.cart_payment_confirm` 并提供收银台入口。沙箱收银台在新标签页打开，买家可以回到原对话发送“查询支付结果”。确认请求只使用当前账号、当前会话的订单。购物车、价格或地址在确认前变动时需要重新报价。

购物车沙箱与报告共用 `ALIPAY_NOTIFY_URL`。当前商品库用于演示。接入商户的实际商品目录和履约系统后，才在生产环境开启 `OMNICART_CART_ALLOW_LIVE_PAYMENT=true`。

## 支付宝沙箱

在 [支付宝开放平台沙箱](https://open.alipay.com/develop/sandbox/tool) 取得应用、沙箱卖家 PID 和买家账号。用 PEM 文件保存应用私钥和支付宝公钥，文件放在版本控制之外。应用通过公钥模式执行 RSA2 验签。

```dotenv
OMNICART_REPORT_PAYMENT_MODE=sandbox
ALIPAY_APP_ID=<沙箱应用 ID>
ALIPAY_SELLER_ID=<沙箱卖家 PID>
ALIPAY_PRIVATE_KEY_PATH=/secure/path/sandbox-merchant-private.pem
ALIPAY_PUBLIC_KEY_PATH=/secure/path/sandbox-alipay-public.pem
ALIPAY_WEB_ORIGIN=http://127.0.0.1:5173
```

服务费由 `OMNICART_REPORT_PRICE_FEN` 配置，默认 199 分。服务端在报价时保存金额和报告快照。“确认订单并前往支付宝”打开沙箱收银台。使用沙箱买家付款，回到报告页会触发服务端查单。如需重试，可点击“查询支付宝付款结果”。参见 [Vibe Pay 网站支付接入指南](https://aipay.alipay.com/docs/vibe-pay/ai-web-app-payment-qianyi/ai-web-app-payment-integration-guide.html)。

有公网 HTTPS 环境时，将 `ALIPAY_NOTIFY_URL` 设置为 `https://你的域名/api/report-payments/alipay/notify`，再验证支付宝异步通知。正式收款需将商户环境改为 `production`，使用已签约的电脑网站支付应用、正式密钥、HTTPS Web 地址和公网通知地址。正式付款由团队在上线验证时确认。

本次联调已打开官方沙箱收银台并验签读取未支付状态。浏览器买家付款仍停在收银台，尚需用沙箱买家通过收银台完成付款并取得成功查单结果。本地使用测试密钥验证了验签、金额核对和重复通知的幂等性。

## Skill Pay 上架

[欧米到手价比较](../skills/omi-price-compare/SKILL.md) 计算标价、运费和使用期成本，并标记未知费用或未核实的硬性条件。用下列命令从项目根目录生成上传包。

```bash
(cd skills/omi-price-compare && zip -X ../../omi-price-compare.zip SKILL.md scripts/compare_costs.py)
```

团队账号需要在 Skill Pay 签署相关协议，提交技能包并通过安全检测。选择一次性付费模式后，平台交付技能文件。审核通过并取得官方分享入口后，将其填入 `OMNICART_REPORT_SKILLPAY_URL`，网页会显示技能入口。随后用买家环境验证购买、安装和比价结果。参见 [Skill Pay 上架与交付说明](https://skillpay.alipay.com/faq)。

## 外部 Agent 购买报告

将 [欧米选购报告下单](../skills/omi-report-order/SKILL.md) 安装到支持 Agent Skills 的环境。配置 `OMNICART_REPORT_BASE_URL` 为商家服务地址，并通过运行环境提供买家已有的 OmniCart Bearer 会话。对 Agent 说“在欧米查找 500 元以内真无线耳机的选购报告，给我看报价”。同意后，由 Agent 创建收银台材料。支付由 [支付宝支付处理技能](https://github.com/alipay/payment-skills/tree/main/alipay-payment-skill) 承接。买家付款后，由 OmniCart 服务端复核订单，确认后才向 Agent 返回报告。

下单 Skill 使用官方 CLI 将已签名的收银台链接转换成 `paymentLink`。Agent 用同一支付会话，将完整短链交给官方支付技能。正式钱包交接需用团队签约应用完成验证。参见 [已有支付服务接入智能体指南](https://aipay.alipay.com/merchant-guide)。
