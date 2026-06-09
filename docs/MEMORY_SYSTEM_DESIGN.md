# OmniCart 记忆系统设计文档（完整版·已实现）

版本：5.0（最终实现版）
更新时间：2026-06-07
状态：✅ 全部完成
更新时间：2026-06-07

---

## 一、设计思路

### 1.1 当前状态

短期记忆已经完整：`ConversationService` 管理一次购物任务内的约束累积、话题切换、追问检测。**唯一做不到的是：用户关了 App 下次打开，偏好全部丢失。**

### 1.2 长期记忆的定位

不做"AI 自动推测你喜欢什么"。只做一件事：**把用户明确表达的偏好，跨会话保存，下次推荐时用上。**

### 1.3 两个来源，不同路径

| 来源 | 触发方式 | 严格程度 |
|---|---|---|
| **手动输入** | 用户在 PreferenceScreen 自由打字 → 点保存 → 调用 Qwen 解析 → 存库 | 宽松：用户主动填的，默认信任 |
| **对话提取** | 对话中包含"记住"、"以后都"、"我一直"等关键词 → 调 Qwen 解析 → 存库 | 严格：必须明确长时信号词，且不含"这次"等临时词 |

### 1.4 使用时的优先级

```
当前轮明确需求 > session 累积约束 > 长期偏好
```

用户说"这次不要 Apple"→ 即使长期偏好 brands=["Apple"]，本轮也不传品牌偏好。

### 1.5 不做的事情

- 不自动从行为推断偏好（3 次加购不算偏好，用户自己会说）
- 不搞置信度/来源/衰减权重/审计日志/使用轨迹
- 不搞 Qdrant 语义索引 / Redis 缓存
- 不搞 Harness 验证
- 不单独部署解析模型

---

## 二、数据库设计

### 2.1 新建表：`user_profiles`

一人一行。偏好不是高频增长的知识图谱，JSONB 足够，查询一条 SQL 搞定。

```sql
CREATE TABLE user_profiles (
    user_id VARCHAR(64) PRIMARY KEY,      -- 用户 ID，匿名用户不创建
    raw_text TEXT DEFAULT '',              -- 用户原始输入，可追溯
    categories JSONB DEFAULT '[]',         -- ["数码电子", "家居"]
    sub_categories JSONB DEFAULT '[]',     -- ["手机", "充电宝", "耳机"]
    brands JSONB DEFAULT '[]',             -- ["Apple", "Anker"]
    devices JSONB DEFAULT '[]',            -- ["iPhone 15", "MacBook Pro"]
    scenarios JSONB DEFAULT '[]',          -- ["出差", "通勤"]
    budget_min FLOAT,
    budget_max FLOAT,
    avoid_tags JSONB DEFAULT '[]',         -- ["太重", "续航短"]
    must_tags JSONB DEFAULT '[]',          -- ["USB-C", "快充"]
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 2.2 与旧表的关系

- **`conversations.context_snapshot`**（短期记忆）：不变，仍由 ConversationService 管理
- **`user_preferences`**（migration 001 建的旧表）：不删也不改，不动它。新表叫 `user_profiles`，完全独立
- **`user_memories` / `memory_audit_logs` / `memory_usage_traces`**（migration 002）：不删，不用，不管

---

## 三、解析设计

### 3.1 复用现有 Qwen-Chat 接口

不新增模型部署，在现有 `ModelGateway` 上加一个 extraction prompt。

### 3.2 System Prompt

```
你是一个购物偏好解析器。从用户输入中提取网购偏好。

规则：
1. 只提取明确提到的，不推测
2. 品类归类参考：
   - 数码电子: 手机/电脑/耳机/充电宝/平板/手表/相机/音箱
   - 家居生活: 灯具/收纳/清洁/床上用品/厨房用品
   - 服饰鞋包: 上衣/裤子/鞋/包/配饰
   - 美妆个护: 护肤品/彩妆/洗发/沐浴
   - 食品饮料: 零食/饮料/生鲜/茶叶
   - 运动户外: 跑步/健身/露营/骑行/游泳
3. 空值用 [] 或 null，不要编造
4. 只输出 JSON，不要其他内容
5. 用户可能用口语表达，请准确理解。例如"喜欢苹果手机"→ brands=["Apple"], devices=["iPhone"], sub_categories=["手机"], categories=["数码电子"]

用户输入: {raw_text}

JSON:
{
  "categories": [],
  "sub_categories": [],
  "brands": [],
  "devices": [],
  "scenarios": [],
  "budget_min": null,
  "budget_max": null,
  "avoid_tags": [],
  "must_tags": []
}
```

### 3.3 JSON 解析容错

模型可能返回格式不完美的 JSON（多了逗号、少了引号、markdown 包裹）。解析时做 3 层 fallback：

1. 直接 `json.loads(response)`
2. 正则提取 `\{[\s\S]*\}` 再 parse
3. 两个都失败 → 返回 None，不写入，不报错

---

## 四、合并策略

用户多次保存偏好时合并而非覆盖。

```python
def merge_profiles(existing: dict, new_fields: dict) -> dict:
    """
    existing: 数据库中已有的 profile dict
    new_fields: 本次解析出的字段 dict
    
    规则:
    - 数组字段 (categories, brands, devices, scenarios, avoid_tags, must_tags, sub_categories):
      union 合并，去重
    - 标量字段 (budget_min, budget_max):
      有值则覆盖
    - raw_text: 追加（用换行分隔）
    """
    result = dict(existing)
    
    array_fields = ["categories", "sub_categories", "brands", "devices", 
                    "scenarios", "avoid_tags", "must_tags"]
    for field in array_fields:
        existing_vals = set(existing.get(field, []))
        new_vals = set(new_fields.get(field, []))
        result[field] = sorted(list(existing_vals | new_vals))
    
    for field in ["budget_min", "budget_max"]:
        if new_fields.get(field) is not None:
            result[field] = new_fields[field]
    
    if new_fields.get("raw_text"):
        if result.get("raw_text"):
            result["raw_text"] = result["raw_text"] + "\n" + new_fields["raw_text"]
        else:
            result["raw_text"] = new_fields["raw_text"]
    
    return result
```

### 删除机制

- **整体重置**：`DELETE /api/preferences/profile?user_id=X` → 删掉整行
- **单项删除**：`DELETE /api/preferences/profile/field?user_id=X&field=brands&value=Apple` → 从 brands 数组中移除 "Apple"

---

## 五、与推荐链路的集成

### 5.1 整体流程

```
POST /api/recommend/v2
  │
  ├─ 1. ConversationService (短期记忆，不变)
  ├─ 2. FollowUpEngine (追问检测，不变)
  │
  ├─ 3. [新] 加载 user_profiles
  │     IF user_id 非空:
  │       profile = UserProfileService.get_profile(user_id)
  │       构建 search_hints + context_hints
  │
  ├─ 4. Agent Workflow
  │     - enriched_query 追加 search_hints (品牌+标签关键词)
  │     - context_prompt 追加 context_hints (完整偏好描述)
  │     - RetrievalAgent: search_hints 自然参与检索
  │     - ResponseAgent: context_hints 用于引用偏好
  │
  ├─ 5. ConversationService 更新 (短期记忆，不变)
  │
  └─ 6. [新] 对话提取检查 (异步，不阻塞响应)
        IF 消息包含长时信号词 AND user_id 非空:
          UserProfileService.parse_and_merge(user_id, message)
          在 answer 末尾追加已更新提示
```

### 5.2 search_hints 构建

从 profile 中提取关键词，追加到 enriched_query。这些关键词会被 RetrievalAgent 的自然语言检索纳入 query 语义，从而影响召回。

```python
def build_search_hints(profile: dict) -> str:
    """构建检索增强关键词（追加到查询文本中）"""
    keywords = []
    # 品牌名天然是检索关键词
    keywords.extend(profile.get("brands", []))
    # 必须标签
    keywords.extend(profile.get("must_tags", []))
    # 场景转关键词
    scenario_map = {
        "出差": "便携 大容量",
        "通勤": "轻便 小巧",
        "运动": "防水 稳固",
        "旅行": "便携 长续航",
    }
    for s in profile.get("scenarios", []):
        if s in scenario_map:
            keywords.extend(scenario_map[s].split())
    # 设备转兼容关键词
    device_map = {
        "iPhone": "Lightning USB-C MFi",
        "MacBook": "USB-C PD快充",
        "iPad": "USB-C",
    }
    for d in profile.get("devices", []):
        for dev_key, kw in device_map.items():
            if dev_key.lower() in d.lower():
                keywords.extend(kw.split())
    
    return " ".join(keywords) if keywords else ""
```

### 5.3 context_hints 构建

构建完整偏好描述，注入 context_prompt。只有 ResponseAgent 会读取，用于在回答中引用偏好。

```python
def build_context_hints(profile: dict) -> str:
    """构建偏好上下文（供 ResponseAgent 引用）"""
    parts = ["[用户长期偏好]"]
    if profile.get("scenarios"):
        parts.append(f"使用场景: {', '.join(profile['scenarios'])}")
    if profile.get("brands"):
        parts.append(f"品牌倾向: {', '.join(profile['brands'])}")
    if profile.get("devices"):
        parts.append(f"设备: {', '.join(profile['devices'])}")
    budget_parts = []
    if profile.get("budget_min"):
        budget_parts.append(f"最低{profile['budget_min']}元")
    if profile.get("budget_max"):
        budget_parts.append(f"最高{profile['budget_max']}元")
    if budget_parts:
        parts.append(f"预算: {'-'.join(budget_parts)}")
    if profile.get("must_tags"):
        parts.append(f"偏好特性: {', '.join(profile['must_tags'])}")
    if profile.get("avoid_tags"):
        parts.append(f"避雷: {', '.join(profile['avoid_tags'])}")
    parts.append("注意: 当前用户明确需求优先于以上长期偏好。")
    return "\n".join(parts)
```

### 5.4 对话提取检查

```python
# 长时信号词（保守）
LONG_TERM_SIGNALS = ["记住", "以后都", "我一直", "永远", "长期", "保存偏好", "以后就", "一直用"]
# 临时信号词（排除）
TEMPORARY_SIGNALS = ["这次", "本轮", "当前", "暂时", "临时", "先"]

def has_long_term_signal(message: str) -> bool:
    """检查消息是否包含长期偏好意图"""
    has_signal = any(s in message for s in LONG_TERM_SIGNALS)
    is_temporary = any(s in message for s in TEMPORARY_SIGNALS)
    return has_signal and not is_temporary and len(message) > 5
```

### 5.5 冲突处理

当前 session 约束已通过 FollowUpEngine 合并到 WorkflowState，长期偏好作为**软增强**叠加在上：

- `search_hints` 只追加关键词，不替换原 query → 原始意图完整保留
- `context_hints` 末尾有"当前需求优先"提示 → ResponseAgent 不会用偏好覆盖用户需求
- 用户说"不要 XX" → RouterAgent 提取的 `exclude_tags` 优先级最高，自然的排他效果

---

## 六、新增文件清单

### 6.1 后端新增

| 文件 | 职责 | 行数 |
|---|---|---|
| `backend/app/models/user_profile.py` | UserProfileModel ORM | ~45 |
| `backend/app/repositories/user_profile_repo.py` | UserProfileRepository (CRUD) | ~80 |
| `backend/app/services/user_profile_service.py` | 解析 + 合并 + 信号检测 | ~200 |
| `backend/app/api/user_profile.py` | REST API (get/save/delete) | ~90 |
| `alembic/versions/004_add_user_profiles.py` | 建表 migration | ~40 |

### 6.2 后端修改

| 文件 | 修改内容 |
|---|---|
| `backend/app/models/__init__.py` | 注册 UserProfileModel |
| `backend/app/main.py` | 注册 user_profile router |
| `backend/app/api/recommend.py` | 加载 profile → 构建 hints → 注入 query/prompt；响应后检查对话提取 |
| `backend/app/api/agent_stream.py` | 同上 |

### 6.3 Android 修改

| 文件 | 修改内容 |
|---|---|
| `PreferenceScreen.kt` | 重新设计：大文本框 + 解析结果卡片 + 字段删除 |
| `PreferenceViewModel.kt` | 适配新 API |
| `OmniCartApi.kt` | 新增 profile API 端点 |

### 6.4 不需要的操作

- 不需要新建 migration 之外的 Alembic 操作
- 不需要修改 Agent Workflow 内部节点（Router/Retrieval/Decision/Response）
- 不需要修改 WorkflowState schema
- 不需要修改 Android ChatScreen / CartScreen / ProfileScreen

---

## 七、API 设计

### 7.1 获取用户偏好

```
GET /api/preferences/profile?user_id=U001
```

Response:
```json
{
  "user_id": "U001",
  "raw_text": "我经常出差，喜欢苹果手机，预算200-500",
  "categories": ["数码电子"],
  "sub_categories": ["手机"],
  "brands": ["Apple"],
  "devices": ["iPhone"],
  "scenarios": ["出差"],
  "budget_min": 200,
  "budget_max": 500,
  "avoid_tags": [],
  "must_tags": [],
  "enabled": true,
  "updated_at": "2026-06-07T15:30:00Z"
}
```

用户不存在时返回 `null`（不是 404）。

### 7.2 保存偏好（手动输入）

```
PUT /api/preferences/profile
{
  "user_id": "U001",
  "raw_text": "我经常出差，喜欢苹果手机，预算200-500"
}
```

流程：解析 raw_text → 与已有 profile 合并 → 存库 → 返回合并后的 profile。

### 7.3 删除偏好字段

```
DELETE /api/preferences/profile/field?user_id=U001&field=brands&value=Apple
```

### 7.4 重置全部偏好

```
DELETE /api/preferences/profile?user_id=U001
```

### 7.5 与现有 preference API 的关系

现有 `GET/PUT/DELETE /api/preferences` 保持不动，仍然管理 **session 级别**的约束（通过 context_snapshot）。

新增的 `/api/preferences/profile` 管理 **长期偏好**。

---

## 八、Android PreferenceScreen 设计

### 8.1 改造方案

当前是分字段输入（品类、预算、场景、标签各一个输入框），改造为**一个自由文本输入框 + 解析结果卡片**。

### 8.2 UI 结构

```
┌─────────────────────────────────────┐
│  购物偏好                     [保存] │
├─────────────────────────────────────┤
│  💡 告诉豆仔你的购物习惯            │
│  例如：我经常出差，喜欢苹果手机，   │
│  预算200-500，不喜欢太重的           │
│                                     │
│  ┌─────────────────────────────────┐│
│  │ 我经常出差，喜欢苹果手机...     ││  ← 自由文本输入
│  └─────────────────────────────────┘│
│                           [保存偏好] │
│                                     │
│  ── 已解析的偏好 ──                 │
│                                     │
│  ┌─ 🏷 品类 ──────────────────────┐ │
│  │  数码电子                     ✕ │ │  ← 可删除
│  └────────────────────────────────┘ │
│  ┌─ 📱 子品类 ────────────────────┐ │
│  │  手机                         ✕ │ │
│  └────────────────────────────────┘ │
│  ┌─ 🏭 品牌 ──────────────────────┐ │
│  │  Apple                        ✕ │ │
│  └────────────────────────────────┘ │
│  ┌─ ✈ 场景 ──────────────────────┐ │
│  │  出差                         ✕ │ │
│  └────────────────────────────────┘ │
│  ┌─ 💰 预算 ──────────────────────┐ │
│  │  200 - 500                    ✕ │ │
│  └────────────────────────────────┘ │
│                                     │
│  [重置全部偏好]                      │
└─────────────────────────────────────┘
```

### 8.3 交互

- 用户输入自由文本 → 点"保存偏好" → 调 `PUT /api/preferences/profile`
- 返回解析结果 → 刷新下方卡片
- 点击卡片上的 ✕ → 调 `DELETE /api/preferences/profile/field` → 刷新
- 用户可再次输入新文本追加偏好 → 合并

---

## 九、推荐链路完整时序

```
Android                          FastAPI                          DB
  │                                 │                              │
  │ POST /api/recommend/v2          │                              │
  │ {user_query, user_id, ...}      │                              │
  ├────────────────────────────────►│                              │
  │                                 │                              │
  │                   短期记忆 (不变)                               │
  │                   ──────────────                               │
  │                   ConversationService.get_or_create             │
  │                   append_user_message                           │
  │                   FollowUpEngine.detect                         │
  │                                 │                              │
  │                   长期记忆 [新]                                 │
  │                   ──────────────                               │
  │                   IF user_id:                                  │
  │                     UserProfileService.get_profile(user_id) ───┤
  │                     ←────────── profile ───────────────────────│
  │                     build_search_hints(profile)                │
  │                     build_context_hints(profile)               │
  │                     enriched_query += search_hints             │
  │                     context_prompt += context_hints            │
  │                                 │                              │
  │                   Agent Workflow (不变)                         │
  │                   ────────────────────                         │
  │                   run_workflow(enriched_query, context_prompt)  │
  │                                 │                              │
  │                   短期记忆 (不变)                               │
  │                   ──────────────                               │
  │                   append_assistant_message                      │
  │                   update_context_snapshot                       │
  │                                 │                              │
  │                   对话提取检查 [新，异步]                        │
  │                   ───────────────────────                       │
  │                   IF has_long_term_signal(message):             │
  │                     parse_and_merge(user_id, message) ─────────┤
  │                     answer += "已更新偏好"                       │
  │                                 │                              │
  │ ←─── response ──────────────────│                              │
  │                                 │                              │
```

---

## 十、实现状态（已完成全部 4 个 Phase）

| Phase | 内容 | 状态 | 新增文件 | 修改文件 |
|---|---|---|---|---|
| 1 | 数据层：表+Model+Repo | ✅ | 3 | 1 |
| 2 | 业务层：UserProfileService | ✅ | 1 | 0 |
| 3 | API + Android UI | ✅ | 1 | 3 |
| 4 | 推荐链路集成 | ✅ | 0 | 2 |

**实际新增代码：~600 行（含后端 + Android）**

### 最终实现的关键设计决策

1. **search_hints 仅用 must_tags** — 品牌/场景/设备不污染搜索 query，只放在 context_hints 供 ResponseAgent 引用
2. **LLM 非标字段映射** — skin_type → must_tags（"油皮肤质适用"），hair_type → must_tags，自动补 categories
3. **输入框与历史分离** — PreferenceScreen 不加载历史 raw_text 到输入框，保持清爽的追加体验
4. **解析 Prompt 增强** — 覆盖美妆/护肤/发质/食品等品类，丰富示例

### 修复的 Bug

| Bug | 根因 | 修复 |
|---|---|---|
| 搜"手机"推荐充电宝 | search_hints 把场景关键词"便携/大容量/快充"塞进 query | search_hints 改用仅 must_tags |
| "油皮敏感肌"丢失 | LLM 返回 skin_type 但 schema 无此字段 | _normalize_fields() 映射到 must_tags |
| null 响应崩溃 | Retrofit 无法将 JSON null 反序列化为 ProfileResponse? | 改用 Response<ProfileResponse?> 包装 |
| 输入框被历史填满 | rawText 加载了全部累积文本 | inputText 独立字段，保存后清空 |
| Qdrant 连接失败 | httpx 走系统代理 | 设 NO_PROXY 环境变量绕过 |

## 十一、测试要点

| 测试场景 | 预期结果 |
|---|---|
| 手动输入"我喜欢索尼耳机" | 解析出 categories=["数码电子"], sub_categories=["耳机"], brands=["Sony"] |
| 手动输入"出差，轻便，预算300" | scenarios=["出差"], must_tags=["轻便"], budget_max=300 |
| 追加输入"也喜欢 Anker" | brands=["Sony", "Anker"]（合并） |
| 对话说"记住，以后都要快充" | 触发提取，更新 must_tags |
| 对话说"这次要便宜的" | 不触发提取（含"这次"） |
| 当前需求"不要 Sony" vs profile brands=["Sony"] | 本轮不传品牌偏好，以当前需求为准 |
| 匿名用户请求 | 跳过所有长期记忆逻辑 |
| 模型返回乱码 JSON | 解析失败 → 静默跳过，不影响推荐 |

---

## 附录：ID 前缀

| 前缀 | 表 | 说明 |
|---|---|---|
| `CONV-` | conversations | 短期记忆 |
| `MSG-` | conversation_messages | 短期记忆 |
| `EVT-` | behavior_events | 短期记忆 |
| — | user_profiles | **无前缀，user_id 直接做主键** |
