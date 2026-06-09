# OmniCart Agent 数据库设计详解

> 更新：2026-06-09 | 数据库：PostgreSQL + Qdrant | ORM：SQLAlchemy 2.0 Async | 迁移：Alembic

---

## 库级设计

### 为什么是 PostgreSQL + Qdrant 双数据库？

| 数据库 | 定位 | 为什么选它 |
|--------|------|-----------|
| **PostgreSQL** | 业务数据主库 | JSONB 存嵌套结构无需拆表、ACID 事务保障购物车/订单一致性、asyncpg 异步驱动高性能、Alembic 迁移框架版本化管理 |
| **Qdrant** | 语义向量检索 | Rust 实现毫秒级 ANN、COSINE 距离度量、本地二进制零运维依赖、REST API 直连无 ORM 开销 |

两者通过 UUID5 确定性的 `point_id` 关联（`uuid5(NAMESPACE, product_id)`），同一商品在 PG 和 Qdrant 中可交叉引用。

### 降级策略

```
DATABASE_URL 为空 → 自动切换 JSON 文件仓库（所有6类仓库都有 PG+内存双实现）
QDRANT_URL 为空   → HybridSearch.text_only 降级为纯 jieba 关键词
任一连接失败       → 捕获异常静默降级，不抛错不阻塞
```

工厂函数模式使得切换无需改业务代码：
```python
def get_product_repo():
    if USE_POSTGRES: return PgProductRepository()
    return JsonProductRepository()
```

---

## 数据表逐一分析

### 1. products — 商品主表

```sql
CREATE TABLE products (
    product_id    VARCHAR(64) PRIMARY KEY,    -- p_beauty_001
    title         TEXT NOT NULL,              -- 商品全称
    brand         VARCHAR(128) NOT NULL,      -- 品牌
    category      VARCHAR(64) NOT NULL,       -- 四大品类
    sub_category  VARCHAR(64),               -- 子品类
    base_price    NUMERIC(10,2) NOT NULL,     -- 基准售价
    image_path    TEXT,                       -- 数据集图片路径
    skus          JSONB,                      -- SKU变体数组
    rag_knowledge JSONB,                      -- RAG知识库
    created_at    TIMESTAMPTZ,
    updated_at    TIMESTAMPTZ
);
```

#### 字段设计理由

| 列 | 类型 | 为什么这样设计 |
|----|------|---------------|
| `product_id` | VARCHAR(64) PK | 语义化ID（`p_beauty_001`），可读可追溯，不用自增数字 |
| `title` | TEXT | 商品名可能很长（如"兰蔻小黑瓶全新精华肌底液..."），VARCHAR(256)不够 |
| `brand` | VARCHAR(128) | 品牌名固定受控（Apple/Nike/兰蔻），128 充足 |
| `category` | VARCHAR(64) INDEX | 四大品类检索最频繁的过滤条件，必须索引 |
| `sub_category` | VARCHAR(64) INDEX | 作为品类下的二级过滤和关键词匹配 boost 依据 |
| `base_price` | NUMERIC(10,2) INDEX | 精确十进制（不用 FLOAT 避免精度问题），索引支持价格区间过滤 |
| `image_path` | TEXT | 仅存相对路径（如 `4_Food_and_Life/images/p_food_001.jpg`）|
| `skus` | **JSONB** | 动态属性（颜色/容量/尺码）无固定 schema，拆表需 EAV 反模式 |
| `rag_knowledge` | **JSONB** | 营销描述+FAQ+评论三层嵌套，拆为 3 张关联表 JOIN 成本高 |

#### 为什么 skus 和 rag_knowledge 用 JSONB 而不是拆表？

**传统范式做法（不采用）：**
```
products ←─ sku_options (EAV: attr_name/attr_value/product_id)
products ←─ product_faqs (question/answer/product_id)
products ←─ product_reviews (nickname/rating/content/product_id)
```

**不拆的理由：**

1. **SKU 属性动态且稳定**：颜色/容量/尺码在写入后几乎不变，适合文档内嵌。EAV 模式需要 `attr_name` + `attr_value` 两张表，查询一个商品的 SKU 需要 JOIN 3 次。

2. **RAG 知识库是一体化读取**：检索时总是一次性读全 product 的 marketing_description + faq + reviews 做全文匹配，拆表每次需要 3 个 SELECT → 3 次网络往返。

3. **数据量可控**：100 件商品 ×（~5 SKU + ~5 FAQ + ~3 评论）= 每个 JSONB 约 2-5KB，全表仅 ~500KB，JSONB 索引都用不上，读取零开销。

4. **JSONB 支持内部查询**：`WHERE skus @> '[{"color": "白色"}]'` 可以过滤 SKU 属性，不需要拆表。

**什么情况下应该拆：** 当商品扩展到 1000+ 件，且需要"按特定规格跨商品搜索"时（如"所有白色 256GB 的手机"），应该拆 `sku_options` 表 + GIN 索引。

#### 索引策略

| 索引 | 类型 | 用途 |
|------|------|------|
| `category` | B-tree | `WHERE category = '数码电子'` 品类筛选 |
| `sub_category` | B-tree | 子品类精确搜索 |
| `base_price` | B-tree | `WHERE base_price <= 500` 预算过滤 |

当前 100 件规模，复合索引不需要。扩展到 10000+ 时建议：`(category, sub_category, base_price)` 复合索引。

---

### 2. cart_items — 购物车表

```sql
CREATE TABLE cart_items (
    cart_item_id  VARCHAR(64) PRIMARY KEY,    -- UUID
    user_id       VARCHAR(64) NOT NULL,        -- 用户（当前demo_user_001）
    product_id    VARCHAR(64) NOT NULL,        -- 关联商品
    sku_id        VARCHAR(64),                -- 选中SKU
    title         VARCHAR(256),               -- 📌 商品名快照
    brand         VARCHAR(128),               -- 📌 品牌快照
    price         NUMERIC(10,2),              -- 📌 加购时价格快照
    image_url     TEXT,                       -- 📌 图片URL快照
    quantity      INTEGER DEFAULT 1,           -- 数量
    selected      BOOLEAN DEFAULT TRUE,        -- 是否选中（用于多选结算）
    created_at    TIMESTAMPTZ,
    updated_at    TIMESTAMPTZ
);
```

#### 核心设计决策：反范式化商品快照

**问题：** 为什么不只存 `product_id`，然后 JOIN products 读价格？

**回答：** 这是电商系统的标准做法——**购物车是快照语义**。

| 场景 | 只存 product_id | 反范式快照 |
|------|----------------|-----------|
| 商品涨价 100 元 | 用户看到的价格变了，可能投诉 | 加购时锁定价格 ✅ |
| 商品下架 | 购物车显示 NULL | 依然能看到历史记录 ✅ |
| 展示购物车 | 每次都需要 JOIN products | 单表查询 ✅ |

`title`/`brand`/`price`/`image_url` 在加购时从 products 表复制一份写入 cart_items。

#### 索引策略

| 索引 | 用途 |
|------|------|
| `user_id` (B-tree) | `WHERE user_id = 'demo_user_001'` 查用户的全部购物车 |

#### selected 字段设计

`selected = TRUE/FALSE` 支持**多选/部分结算**。用户可以只勾选 3 件中的 2 件去结算，第 3 件留在购物车。全选/取消全选通过 `SELECT ALL` 批量修改。

---

### 3. users — 用户表

```sql
CREATE TABLE users (
    user_id       VARCHAR(64) PRIMARY KEY,     -- user_xxxxxxxxxxxx
    username      VARCHAR(64) UNIQUE NOT NULL,  -- 登录名
    password_hash VARCHAR(256) NOT NULL,        -- PBKDF2-SHA256 哈希
    email         VARCHAR(128) DEFAULT '',      -- 邮箱（选填）
    phone         VARCHAR(32) DEFAULT '',       -- 手机号（选填）
    avatar_url    VARCHAR(512) DEFAULT '',      -- 头像
    is_active     BOOLEAN DEFAULT TRUE,         -- 软删除标记
    token         VARCHAR(128) DEFAULT '',      -- Bearer Token
    created_at    TIMESTAMPTZ,
    updated_at    TIMESTAMPTZ
);
```

#### 字段设计理由

| 列 | 为什么 |
|----|--------|
| `user_id` | 自生成（`user_` + UUID前12位），不依赖数据库自增，分布式友好 |
| `username` UNIQUE INDEX | 登录唯一标识，需要索引加速查询 |
| `password_hash` 256 | PBKDF2-SHA256 × 100000 迭代，hash+salt 的长度约 120 字符，256 充足 |
| `email`/`phone` 默认空 | 比赛版非强制，简化注册流程 |
| `is_active` | 软删除——禁用账号不清除数据 |
| `token` | 登录时生成 `secrets.token_hex(32)` 64 位 Bearer Token |

#### 为什么不用 JWT？

比赛场景无过期/刷新/黑名单需求。简单 Token 足够：每次登录刷新，SharedPreferences 持久化，OkHttp 拦截器注入 `Authorization: Bearer <token>`。

#### 为什么用 PBKDF2 而不是 bcrypt？

`hashlib.pbkdf2_hmac()` 是 Python 标准库，零外部依赖。100000 次迭代 + SHA256 + 16 字节盐，安全性对比赛场景足够。生产环境应替换为 bcrypt 或 argon2。

#### 索引策略

| 索引 | 用途 |
|------|------|
| `username` UNIQUE | `WHERE username = 'alice'` 登录查询 |
| `token`（建议加） | `WHERE token = 'xxx'` 鉴权查询（1000+ 用户时必要） |

---

### 4. addresses — 收货地址表

```sql
CREATE TABLE addresses (
    address_id   VARCHAR(64) PRIMARY KEY,      -- addr_xxxxxxxxxxxx
    user_id      VARCHAR(64) NOT NULL,          -- 属于谁
    name         VARCHAR(64) NOT NULL,          -- 收货人
    phone        VARCHAR(32) NOT NULL,          -- 收货电话
    province     VARCHAR(32) DEFAULT '',        -- 省
    city         VARCHAR(32) DEFAULT '',        -- 市
    district     VARCHAR(32) DEFAULT '',        -- 区
    detail       VARCHAR(256) DEFAULT '',       -- 详细地址
    is_default   BOOLEAN DEFAULT FALSE,         -- 默认地址
    created_at   TIMESTAMPTZ,
    updated_at   TIMESTAMPTZ
);
```

#### 字段设计理由

| 列 | 为什么 |
|----|--------|
| `name` + `phone` | 收货人可能不是账户本人（帮家人下单），独立字段有必要 |
| **省/市/区/详细 四段式** | 中国标准地址结构。不存街道办级别（数据维护成本高，值不值得取决于精确度需求） |
| `province` 32 字符 | "新疆维吾尔自治区" 9 个中文字 = 27 字节，32 刚够 |
| `detail` VARCHAR(256) | "某某街道某某小区某某栋某单元某室" 一般不超过 80 字符，256 宽裕 |
| `is_default` | 结算时自动选默认地址，同用户其他地址自动取消 |

#### 默认地址互斥逻辑

仓库层保证同一用户只有一个默认地址：
```python
# 新增/修改时
if new_data.get("is_default"):
    # 1. 先清除同一用户所有其他地址的 is_default
    UPDATE addresses SET is_default = FALSE WHERE user_id = ? AND address_id != ?
    # 2. 再设置当前地址为默认
```

#### 索引策略

| 索引 | 用途 |
|------|------|
| `user_id` (B-tree) | `WHERE user_id = 'xxx'` 查用户的全部地址 |

---

### 5. user_preferences — 用户偏好表

```sql
CREATE TABLE user_preferences (
    id           SERIAL PRIMARY KEY,            -- 自增ID
    session_id   VARCHAR(64) NOT NULL,          -- 会话ID
    user_id      VARCHAR(64),                  -- 登录用户（匿名则为null）
    preferences  JSONB NOT NULL DEFAULT '{}',   -- 偏好JSON
    created_at   TIMESTAMPTZ,
    updated_at   TIMESTAMPTZ,
    UNIQUE (session_id, user_id)
);
```

#### 字段设计理由

| 列 | 为什么 |
|----|--------|
| `id` SERIAL PK | 内部自增 ID，对外暴露 session_id |
| `session_id` + `user_id` UNIQUE | 同一会话+同一用户只有一条偏好记录，支持 UPSERT |
| `preferences` JSONB | 偏好是动态 key-value（category/budget/scenario/tags...），JSONB 天然适应。不用拆表：每条记录的数据量很小（< 1KB），写入频率低 |
| `user_id` 可为 NULL | 匿名用户用 session_id 关联 |

#### 存储的偏好结构

```json
{
  "category": "数码电子",
  "sub_category": "真无线耳机",
  "budget_max": 500.0,
  "scenario": "commute",
  "must_tags": ["降噪", "轻便"],
  "exclude_tags": []
}
```

#### 长期用户偏好 — user_preference_entries

已实现条目化偏好存储（详见 `MEMORY_SYSTEM.md`），每条偏好独立 entry_id，支持品类感知注入、启用/禁用、单独删除。

---

### 6. orders — 订单表

```sql
CREATE TABLE orders (
    order_id    VARCHAR(64) PRIMARY KEY,       -- ORD-XXXXXXXX
    user_id     VARCHAR(128) NOT NULL,
    items       JSONB NOT NULL,                -- [{product_id,title,brand,price,quantity}]
    total_price DOUBLE PRECISION NOT NULL,
    status      VARCHAR(32) DEFAULT 'pending', -- pending/shipped/completed
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

仅模拟下单，不接入真实支付。订单在 checkout 时持久化，Android OrderScreen 从 `GET /api/orders` 读取。

---

### 7. conversations — 会话表 + context_snapshot

```sql
CREATE TABLE conversations (
    conversation_id  VARCHAR(64) PRIMARY KEY,  -- CONV-xxxxxxxxxxxx
    user_id          VARCHAR(128) NOT NULL,
    session_id       VARCHAR(64),
    title            VARCHAR(256),
    status           VARCHAR(32) DEFAULT 'active',
    summary          TEXT,
    context_snapshot JSONB DEFAULT '{}',       -- 短期记忆核心
    last_message     TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ
);
```

`context_snapshot` (JSONB) 是短期记忆核心，存储：约束(constraints)、上轮对话(last_query/last_answer)、商品列表(last_products)、待回答问题(pending_question)、最近3轮摘要(recent_turns)、对话摘要(conversation_summary)。

### 8. conversation_messages — 消息表

```sql
CREATE TABLE conversation_messages (
    message_id      VARCHAR(64) PRIMARY KEY,
    conversation_id VARCHAR(64) REFERENCES conversations,
    user_id         VARCHAR(128),
    session_id      VARCHAR(64),
    role            VARCHAR(16),               -- user / assistant
    content         TEXT,
    image_url       TEXT,
    product_refs    JSONB,                      -- [product_id, ...]
    evidence_refs   JSONB,
    memory_refs     JSONB,
    extra_data      JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

消息支持图片、商品引用、证据引用、记忆引用。Android 会话恢复时从 `GET /api/conversations/{id}/messages` 加载历史。

---

### alembic_version — 迁移版本表

由 Alembic 自动管理，记录当前数据库的迁移版本号。每次 `alembic upgrade head` 检查此表决定需要执行哪些迁移。

---

## Qdrant 向量库配置

```
Collection: products
维度: 1024（匹配 text-embedding-v4 输出）
距离度量: COSINE
point_id: UUID5(NAMESPACE_DNS, product.product_id) — 确定性的，与 PG ID 可互查
索引数据: 100 条向量
嵌入文本: "product_id | title brand category sub_category marketing_description"
构建脚本: scripts/seed_qdrant.py
```

### 为什么 COSINE 而不是 Euclidean？

文本嵌入的方向比绝对位置更重要。两个商品描述的主题相似性由向量方向决定，COSINE 天然适合。

### 为什么 1024 维？

`text-embedding-v4` 输出固定 1024 维。如果用其他嵌入模型需要重建 collection。

### Qdrant 不可用时的降级

```python
if not vector_repo.health_check():
    return text_results[:top_k]  # 纯 jieba 关键词兜底
```

---

## 表关系图

```
users ──1:N──→ addresses        (user_id)
users ──1:N──→ cart_items       (user_id)
users ──1:1──→ user_preferences (session_id + user_id)

products ──N:M──→ cart_items    (product_id, 快照语义)

Qdrant ←── UUID5(product_id) ──→ products
```

无外键约束——比赛版跨表查询不多，Repository 层在 Python 侧做关联验证。生产环境应添加 `FOREIGN KEY`。

---

## 后续优化建议

### 短期（V1 → 答辩前）

| 优化 | 收益 | 工作量 |
|------|------|--------|
| `users.token` 加 B-tree 索引 | 1000+ 用户时 profile 查询加速 | 1 条 SQL |
| `cart_items.product_id` 加索引 | 分析"哪个商品被加购最多" | 1 条 SQL |
| `products.title` 加 GIN trigram 索引 | `ILIKE '%关键词%'` 模糊搜索 | `CREATE EXTENSION pg_trgm` |

### 中期（比赛后 → 线上部署）

| 优化 | 收益 | 工作量 |
|------|------|--------|
| **拆 user_reviews 独立表** | `reviews(product_id, rating, content, user_id, created_at)` 支持跨商品评论分析、按评分排序 | 1 张新表 + 数据迁移 + seed 脚本 |
| **拆 official_faq 独立表** | FAQ 全文检索不再依赖 JSONB 扫描 | 同上 |
| **user_behaviors 行为表** | `(user_id, action, product_id, timestamp, session_id)` 埋点用户点击/加购/浏览 | 1 张新表 + API 埋点 |
| **GIN 索引 on skus** | `WHERE skus @> '[{"color": "白色"}]'` 跨商品 SKU 搜索 | 1 条 SQL |
| **Redis 缓存层** | 热门商品/偏好/Demo Pack 缓存，API 响应从 500ms → 10ms | `redis-py` + Redis 实例 |

### 长期（V3 → 生产级）

| 优化 | 收益 | 工作量 |
|------|------|--------|
| **外键约束** | 数据一致性的最后一道防线 | 4 条 ALTER TABLE |
| **products 分表**（按 category） | 百万商品时的查询性能 | 表分区 |
| **cart_items TTL** | 自动清理 30 天未更新的废弃购物车 | pg_cron |
| **物化视图** | "各品类 Top10 加购商品" 预计算，秒出 | `CREATE MATERIALIZED VIEW` |
| **Connection Pool 调优** | SQLAlchemy pool_size + max_overflow 根据实际并发调整 | 配置文件 |
| **读写分离** | 检索走只读副本，写入走主库 | PG 主从 + pgpool-II |

### ORM 层面优化

```python
# 当前：每次请求 await session.execute(select(...)).first()
# 优化：async SQLAlchemy 2.0 原生支持 eager loading
result = await session.execute(
    select(ProductModel).options(
        selectinload(ProductModel.reviews)  # 一次查询联表
    ).where(...)
)
```

---

## 快速 SQL 查询示例

```sql
-- 各品类商品数
SELECT category, count(*) FROM products GROUP BY category;

-- 数码电子 Top 5 高价商品
SELECT title, brand, base_price FROM products
WHERE category = '数码电子' ORDER BY base_price DESC LIMIT 5;

-- 当前用户购物车（含选中合计）
SELECT c.title, c.price, c.quantity, (c.price * c.quantity) AS subtotal
FROM cart_items c WHERE user_id = 'demo_user_001' AND selected = TRUE;

-- 注册用户列表
SELECT username, email, phone, created_at FROM users ORDER BY created_at DESC;

-- 某用户全部地址
SELECT name, phone, province||city||district||detail AS full_addr, is_default
FROM addresses WHERE user_id = 'user_xxx' ORDER BY is_default DESC;
```
