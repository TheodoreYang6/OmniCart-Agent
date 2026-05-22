# Decision Log

## ADR-008：客户端从 Next.js Web 切换到 Android Native
日期：2026-05-20 · 状态：accepted

### 背景
根据最新交付约束 (1.txt)，客户端必须使用 Android 原生框架开发，不能使用 Web、WebView、React Native、Expo、Flutter 等方案作为主交付端。

### 决策
- **客户端：** Kotlin + Jetpack Compose + Material 3 + MVVM
- **网络：** Retrofit + OkHttp + Kotlin Coroutines
- **图片：** Coil
- **图片选择：** Android Photo Picker (V1)
- **后端：** FastAPI 不变

### 原因
- 比赛明确要求原生客户端
- Jetpack Compose 是 Google 推荐的现代 Android UI 框架
- MVVM + StateFlow 与 Compose 配合最紧密
- Retrofit 是 Android 生态最成熟的网络库
- Coil 是 Kotlin-first 的图片加载库

### 影响
- `frontend/` 标记废弃，不再维护
- 新增 `android-client/` 目录
- CLAUDE.md 全面更新
- run.py 的前端启动部分已不可用
- 所有 V1 展示面板 (Evidence/Trace/Skill/Harness) 改为在 Android 端实现

### 替代方案对比
| 方案 | 优点 | 缺点 | 决定 |
|---|---|---|---|
| Kotlin + Jetpack Compose | Google 官方推荐、MVVM原生支持 | 需要 Android SDK | **采纳** |
| React Native | 跨平台、JS生态 | 非原生、比赛明确禁止 | 拒绝 |
| Flutter | 跨平台、性能好 | 非原生、比赛明确禁止 | 拒绝 |
| iOS SwiftUI | Apple 原生 | 仅限 V2/V3 扩展 | 延后 |

---

## ADR-007：Embedding 走原生 API，Reranker 走兼容 API
日期：2026-05-20 · 状态：accepted
→ Chat/Vision/Embedding→原生API，Reranker→兼容API

## ADR-006：模型配置统一到 YAML 文件
日期：2026-05-20 · 状态：accepted
→ 7 个能力→模型映射，换模型只改一个文件

## ADR-005：pip 使用 --proxy="" 绕过系统代理
日期：2026-05-20 · 状态：accepted

## ADR-004：使用 .pth 文件自动注入 sys.path
日期：2026-05-20 · 状态：accepted

## ADR-003：前端使用系统字体
日期：2026-05-20 · 状态：superseded (前端已废弃)

## ADR-002：V0 默认启用 Mock Mode
日期：2026-05-20 · 状态：accepted

## ADR-001：V0 使用关键词匹配替代向量检索
日期：2026-05-20 · 状态：accepted
