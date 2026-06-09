# OmniCart 记忆系统设计文档

## 概述

OmniCart 采用三层记忆架构，覆盖从单轮追问到跨会话偏好持久化的全场景：

| 层次 | 存储 | 粒度 | TTL | 用途 |
|------|------|------|-----|------|
| **短期记忆** | context_snapshot (PG JSONB) | 会话级 | 单次会话 | 品类继承、指代消解、多轮追问 |
| **长期记忆** | user_preference_entries (PG) | 用户级 | 永久 | 品类偏好、品牌偏好、避雷标签 |
| **会话记忆** | conversations + messages (PG) | 会话级 | 永久 | 对话历史、消息持久化、会话恢复 |

三层协同工作：短期记忆让追问自然连贯，长期记忆让推荐个性化，会话记忆让用户可以随时回到之前的对话。

---

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    记忆系统架构                           │
│                                                          │
│  ┌──────────────────┐                                    │
│  │   Android Client  │                                    │
│  │                   │                                    │
│  │ PreferenceScreen  │← 自然语言输入 → Qwen解析 → 条目化  │
│  │ ConversationList  │← 会话列表/切换/删除                │
│  │ Chat History      │← 消息加载/恢复                     │
│  └────────┬──────────┘                                    │
│           │ HTTP REST                                     │
│  ┌────────▼──────────────────────────────────────────┐   │
│  │              FastAPI Backend                        │   │
│  │                                                      │   │
│  │  ┌─────────────────┐  ┌──────────────────────────┐  │   │
│  │  │ConversationSvc  │  │  UserProfileService       │  │   │
│  │  │                 │  │                            │  │   │
│  │  │· get_or_create  │  │  · inject_profile_hints()  │  │   │
│  │  │· append_message │  │  · parse_and_save()        │  │   │
│  │  │· merge_constr.. │  │  · list_entries()          │  │   │
│  │  │· aupdate_snap.. │  │  · detect_category()       │  │   │
│  │  └────────┬────────┘  └────────────┬─────────────┘  │   │
│  │           │                        │                  │   │
│  │  ┌────────▼────────────────────────▼─────────────┐  │   │
│  │  │              FollowUpEngine                     │  │   │
│  │  │  7种追问模式检测 + 约束继承 + 品类切换            │  │   │
│  │  └────────────────────┬───────────────────────────┘  │   │
│  │                       │                               │   │
│  │  ┌────────────────────▼───────────────────────────┐  │   │
│  │  │          Context Compressor                      │  │   │
│  │  │  qwen-turbo 增量摘要 → conversation_summary       │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                    │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │                  PostgreSQL                            │   │
│  │                                                         │   │
│  │  ┌──────────────────┐ ┌─────────────────────────────┐ │   │
│  │  │ conversations     │ │ user_preference_entries      │ │   │
│  │  │ · context_snapshot│ │ · user_id, entry_id          │ │   │
│  │  │   (JSONB)         │ │ · category, brands, devices  │ │   │
│  │  │ · last_message    │ │ · avoid_tags, must_tags      │ │   │
│  │  └──────────────────┘ │ · budget, scenarios           │ │   │
│  │                       │ · enabled, raw_text           │ │   │
│  │  ┌──────────────────┐ └─────────────────────────────┘ │   │
│  │  │ conversation_     │                                  │   │
│  │  │ messages          │                                  │   │
│  │  │ · role, content   │                                  │   │
│  │  │ · product_refs    │                                  │   │
│  │  │ · evidence_refs   │                                  │   │
│  │  └──────────────────┘                                  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 一、短期记忆 — context_snapshot

### 数据模型

`conversations` 表的 `context_snapshot` 列 (JSONB)：

```json
{
  "constraints": {
    "category": "服饰运动",
    "sub_category": "跑步鞋",
    "budget_max": 500,
    "scenario": "sport",
    "must_tags": [],
    "exclude_tags": ["李宁"]
  },
  "last_query": "500以内的轻便跑鞋",
  "last_answer": "推荐Nike Air Zoom Pegasus 41...",
  "last_intent": "recommend",
  "last_products": [
    {"product_id": "p_001", "title": "Nike Air Zoom...", "brand": "Nike", "price": 899}
  ],
  "current_turn": {"category": "服饰运动", "sub_category": "跑步鞋"},
  "pending_question": "要不要帮你推荐一些零食呢？",
  "recent_turns": [
    {"user_query": "...", "assistant_answer": "...", "product_ids": [...]}
  ],
  "conversation_summary": "用户想买轻便跑鞋，预算500以内..."
}
```

### 读写流程

**写入** (每轮 SSE 响应结束后):

```python
# agent_stream.py
snapshot_update = {
    "last_query": req.message,
    "last_answer": answer[-500:],
    "last_intent": state.intent,
    "last_products": structured_products[:10],
    "current_turn": {"category": c.category, "sub_category": c.sub_category, ...},
    "pending_question": _extract_question(answer),
    "recent_turns": recent_turns[-3:],
}
await conv_svc.aupdate_context_snapshot(cid, snapshot_update)
```

**读取** (下一轮 Router 初始化):

```python
# router_agent.py _build_session_context
snapshot = conv_svc.get_context_snapshot_sync(cid)
# → 注入 LLM Prompt: "当前话题品类: 服饰运动\n上轮用户说了: 500以内的轻便跑鞋"
```

### 约束继承

FollowUpEngine 检测追问模式后，智能合并约束：

```
用户: "便宜一点的" → 继承category=跑步鞋, 降低budget_max=300
用户: "有什么好吃的" → 品类切换检测 → 清除旧约束
```

**品类切换规则**: 当前 query 中含明确的新品类关键词时，清空旧约束。否则继承。

**子品类继承规则**: 当前 query 包含子品类关键词时才继承旧子品类(防止"T恤"锁死)。

### 肯定回复处理

豆仔问了问题后，用户回复简短肯定词("要/好/行/可以")的链路：

```
1. _extract_question → 提取 pending_question
2. 下一轮 Router 检测 pending_question + 肯定词
3. state.user_query 自动替换为 pending_question 内容
4. 正常走推荐流程
```

---

## 二、长期记忆 — user_preference_entries

### 设计理念

**条目化**: 每条偏好是独立条目(entry_id)，而非一人一行 JSONB。好处：
- 可单独启用/禁用
- 可单独删除
- 品类感知注入时精准匹配

### 数据模型

```sql
CREATE TABLE user_preference_entries (
    id SERIAL PRIMARY KEY,
    entry_id VARCHAR(64) UNIQUE,
    user_id VARCHAR(128),
    raw_text TEXT,              -- 用户原始输入
    category VARCHAR(64),       -- 品类
    sub_category VARCHAR(128),
    brands TEXT[],              -- 偏好品牌
    devices TEXT[],             -- 偏好设备
    scenarios TEXT[],           -- 偏好场景
    budget_min DOUBLE PRECISION,
    budget_max DOUBLE PRECISION,
    avoid_tags TEXT[],          -- 避雷标签
    must_tags TEXT[],           -- 必须包含的标签
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);
```

### 解析流程

```
Android 文本输入 → Qwen解析 → 结构化预览 → 用户确认 → 保存条目
```

Android PreferenceScreen 流程：
1. 用户输入 "我是油皮敏感肌，喜欢兰蔻和雅诗兰黛，不喜欢韩系品牌"
2. 点击"解析" → 后端 `parse_only()` → Qwen 提取结构化字段
3. 预览显示: category=美妆护肤, brands=[兰蔻,雅诗兰黛], avoid_tags=[韩系品牌]
4. 用户点击"保存" → `savePreferenceEntry()` → 写入 DB

### 品类感知注入

推荐时根据 query 品类精准注入，避免无关偏好污染：

```python
# UserProfileService.inject_profile_hints()
category = detect_category_from_query("推荐蓝牙耳机")  → "数码电子"
entries = list_entries(user_id, category="数码电子")    → 只取数码电子条目
→ 注入 must_tags=["降噪"], brands=["Sony","Bose"]
```

**关键设计**: 未检测到品类时不注入任何偏好，避免"油皮"偏好污染手机搜索。

### search_hints 与 context_prompt 分离

| 注入方式 | 内容 | 用途 |
|----------|------|------|
| search_hints (追加到 query) | must_tags, brands | 直接影响检索召回 |
| context_prompt (追加到上下文) | category, scenario, budget | 影响 LLM 理解和评分 |

场景关键词不放入 search_hints——防止"出差→便携/大容量"导致搜索充电宝时手机被挤下去。

---

## 三、会话记忆 — conversations + messages

### 数据模型

**conversations 表**:
```sql
conversation_id, user_id, session_id, title, status,
context_snapshot (JSONB), last_message, created_at, updated_at
```

**conversation_messages 表**:
```sql
id, conversation_id, user_id, role, content,
image_url, product_refs, evidence_refs, memory_refs, created_at
```

### Android 会话管理

- **ConversationListSheet**: 底部弹出会话列表，显示标题+最后消息
- **会话切换**: 点击历史会话 → 加载消息列表 → 恢复聊天状态
- **新会话**: 一键清空当前对话，开始新话题
- **删除**: 长按删除不需要的会话

### 会话恢复

```python
# 加载历史会话
messages = GET /api/conversations/{cid}/messages
→ ChatViewModel.loadConversation(cid)
→ 映射为 ChatMessage 列表 → 渲染
```

---

## 四、FollowUpEngine — 追问模式检测

### 7 种追问模式

| 优先级 | 模式 | 示例 | 处理逻辑 |
|--------|------|------|---------|
| 1 | ordinal_ref | "第二个怎么样" | 从last_products取对应商品 |
| 2 | brand_ref / title_ref | "那个Nike的" | 按品牌/标题匹配 |
| 3 | last_ref | "刚才那个" | 取last_products[0] |
| 4 | budget_update | "换成200以内" | 继承品类,更新预算 |
| 5 | cart_intent | "加入购物车" | 标记加购意图 |
| 6 | compare | "和刚才那个比" | 继承对比上下文 |
| 7 | vague_followup | "便宜一点" | 继承品类,品质调整 |

### 约束合并策略

```python
# ConversationService.merge_constraints()
if is_topic_switch(new_query, old_category):
    # 话题切换 → 清空旧约束
    return new_constraints
else:
    # 追问 → 合并约束 (new优先, old兜底)
    return merge(old_constraints, new_constraints)
```

### 并发优化

FollowUpEngine 和 Profile injection 并行执行：

```python
follow_up, hints_result = await asyncio.gather(
    _run_followup(),   # FollowUpEngine.detect()
    _run_profile(),    # UserProfileService.inject_profile_hints()
)
```

节省 ~150ms。

---

## 五、Context Compressor — 上下文压缩

### 增量摘要

长对话时，qwen-turbo 异步生成增量摘要：

```
上一轮摘要: "用户想买跑鞋, 预算500以内..."
本轮对话: "便宜一点的呢？" → 推荐 ¥300 特步
新摘要: "用户想买跑鞋, 预算降至300, 已推荐特步160X..."
```

### 异步执行

压缩任务在 SSE 响应完成后通过 `asyncio.create_task` 后台执行，不阻塞用户看到回复。

---

## 六、Android 端实现

### PreferenceScreen

- 自由文本输入框 → "我是油皮敏感肌，喜欢兰蔻和雅诗兰黛"
- "解析"按钮 → `parsePreference(raw_text)` → Qwen 结构化预览
- 预览卡片 → category/brands/avoid_tags → 用户确认
- "保存"按钮 → `savePreferenceEntry(...)` → 写入 DB
- 已保存条目列表 → 可删除/查看

### ConversationListSheet

- 会话列表 → 标题 + 最后消息预览
- 点击切换会话 → `loadConversation(cid)` → 恢复消息
- "新对话"按钮 → 清空状态
- 长按删除 → `deleteConversation(cid)`

### 记忆相关 SSE 字段

每轮 SSE result 返回记忆追踪数据：

```json
{
  "used_memories": ["PREF-xxx: 偏好蓝牙耳机品牌Sony"],
  "blocked_memories": [],
  "memory_trace": {
    "profile_hints": "category=数码电子, brands=[Sony]",
    "followup_detected": false
  }
}
```

Android AgentInsightSheet 的"记忆追溯"标签页可查看。

---

## 关键设计决策

1. **条目化 vs 一行JSONB**: 条目化更灵活——单条增删改不影响其他,品类感知精准匹配
2. **品类感知注入 vs 全量注入**: 品类感知避免"油皮"污染手机搜索,"出差"污染护肤品搜索
3. **search_hints 与 context_prompt 分离**: 场景词只放 context(影响LLM),不放 search(不污染检索)
4. **肯定回复替换**: pending_question 检测 + 肯定词 → 直接替换 query,而不是靠 LLM 理解
5. **异步压缩 vs 同步压缩**: 后台压缩不阻塞对话,用户感知延迟为 0
