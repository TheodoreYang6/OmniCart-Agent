# 欧米选购报告与支付宝接入

选购报告按品类和商品预算免费生成，报告记录保留当次的参考价格、常见问答和评价样本。购物车使用支付宝网站收银台，服务端通过验签通知或查单确认订单。实现见 [报告生成](../backend/app/services/shopping_report.py) 和 [购物车支付 API](../backend/app/api/cart_payments.py)。

| 入口 | 交付内容 | 平台接入 |
| --- | --- | --- |
| Web 和外部 Agent 选购报告 | 可重复查看的免费报告 | 欧米报告服务 |
| 对话和购物车结算 | 购物订单和交易状态 | 支付宝电脑网站支付 |
| 欧米到手价比较 | 可在 Agent 中运行的成本对照技能 | Skill Pay 一次性付费，提交技能包后由平台审核并交付 |

## 本地演示

准备有商品数据的 PostgreSQL。已有 OmniCart 数据栈可继续使用。旧版自动建表的数据库请先按下方流程迁移。安装本次新增的 Python 依赖，并从项目根目录运行迁移。

```bash
python -m pip install -r requirements.txt
alembic upgrade head
```

打开 [选购报告](http://127.0.0.1:5173/reports)，登录后选择“真无线耳机”和商品预算 ¥500，再点击“免费生成报告”。完成后可从报告记录重新查看。在对话中说“我想看看选购报告”，也可以打开报告页。

如需演示购物车结算，在本机 `.env` 设置 `OMNICART_REPORT_PAYMENT_MODE=demo`，再用回环地址启动应用。配置项见 [环境变量样例](../.env.example)。

## 升级没有 Alembic 版本记录的旧数据库

已通过 Alembic 管理的数据库直接运行 `alembic upgrade head`。如果旧版应用通过 ORM 自动建表，且 `alembic_version` 不存在或为空，先备份旧库并暂停写入。保留旧库作为回滚来源，在新建的空数据库上运行迁移后导入应用数据。避免用 `alembic stamp` 跳过建表迁移。

以下命令适用于自动建表生成的 PostgreSQL `public` 表结构。把 `LEGACY_DSN` 和 `TARGET_DSN` 分别设置为旧库和新库的 PostgreSQL 连接串（`postgresql://`）。`TARGET_DSN` 必须指向一个空数据库。用 PostgreSQL 16 或更新版本的客户端，且客户端版本不低于源库服务器版本。

```bash
(
  set -e
  umask 077
  DATABASE_URL="postgresql+asyncpg://${TARGET_DSN#postgresql://}" alembic upgrade head
  pg_dump --dbname="$LEGACY_DSN" --data-only --strict-names --no-owner --no-privileges \
    --table=public.users --table=public.addresses --table=public.products --table=public.cart_items \
    --table=public.orders --table=public.conversations --table=public.conversation_messages \
    --table=public.conversation_context_checkpoints --table=public.user_preference_entries \
    --table=public.product_identities --table=public.product_aliases --table=public.product_facts \
    --file=omnicart-legacy-data.sql
  psql --dbname="$TARGET_DSN" -X --single-transaction --set ON_ERROR_STOP=1 \
    --command='ALTER TABLE public.cart_items ALTER COLUMN sku_label DROP NOT NULL' \
    --file=omnicart-legacy-data.sql \
    --command="UPDATE public.cart_items SET sku_label = '' WHERE sku_label IS NULL" \
    --command='ALTER TABLE public.cart_items ALTER COLUMN sku_label SET NOT NULL'
)
```

检查导入命令的退出状态，核对表行数，并验证登录、地址、购物车、历史订单和对话后，再将应用切到新库。数据转储包含账户和收货信息，应按数据库备份保管。如果旧库有手工改过的表结构，先在数据库副本上验证导入。初次迁移和导入时若报错，应用继续使用旧库。

## 购物车与对话支付

登录后保存收货地址，在 [购物车](http://127.0.0.1:5173/cart) 勾选商品并点击“支付宝结算”。核对商品、收货地址和金额，再确认支付。演示环境可点击“模拟付款成功”。付款确认后，订单进入“我的订单”，购物车会移除已付款且未变更的商品行。

在 [欧米对话](http://127.0.0.1:5173/chat) 发送“用支付宝结算购物车”。欧米展示报价和“支付宝支付”按钮。点击按钮，在对话内核对商品、地址和金额。点击“确认并前往支付宝”，打开与购物车共用的官方收银台。支付宝返回后，对话会重新打开该支付弹窗并主动查单。也可以在对话里说“查询支付结果”。购物车、价格或地址在确认前变动时需要重新报价。

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

点击购物车或对话中的“确认并前往支付宝”打开沙箱收银台。付款返回后会触发服务端查单，也可点击“查询支付结果”。参见 [Vibe Pay 网站支付接入指南](https://aipay.alipay.com/docs/vibe-pay/ai-web-app-payment-qianyi/ai-web-app-payment-integration-guide.html)。

有公网 HTTPS 环境时，将 `ALIPAY_NOTIFY_URL` 设置为 `https://你的域名/api/report-payments/alipay/notify`，再验证支付宝异步通知。正式收款需将商户环境改为 `production`，使用已签约的电脑网站支付应用、正式密钥、HTTPS Web 地址和公网通知地址。正式付款由团队在上线验证时确认。

沙箱验收需由沙箱买家在收银台付款。分别从对话和购物车启动一笔独立支付，验证返回后的付款状态、交易号及购物车变化。

## Skill Pay 上架

[欧米到手价比较](../skills/omi-price-compare/SKILL.md) 计算标价、运费和使用期成本，并标记未知费用或未核实的硬性条件。用下列命令从项目根目录生成上传包。

```bash
(cd skills/omi-price-compare && zip -X ../../omi-price-compare.zip SKILL.md scripts/compare_costs.py)
```

团队账号需要在 Skill Pay 签署相关协议，提交技能包并通过安全检测。选择一次性付费模式后，平台交付技能文件。审核通过并取得官方分享入口后，将其填入 `OMNICART_REPORT_SKILLPAY_URL`，网页会显示技能入口。随后用买家环境验证购买、安装和比价结果。参见 [Skill Pay 上架与交付说明](https://skillpay.alipay.com/faq)。

## 外部 Agent 生成报告

将 [欧米选购报告](../skills/omi-report-order/SKILL.md) 安装到支持 Agent Skills 的环境。配置 `OMNICART_REPORT_BASE_URL` 为服务地址，并通过运行环境提供用户已有的 OmniCart Bearer 会话。对 Agent 说“在欧米生成一份 500 元以内的真无线耳机选购报告”。接口直接返回报告和报告编号。
