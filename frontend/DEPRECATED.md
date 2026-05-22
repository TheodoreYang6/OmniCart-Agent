# DEPRECATED — frontend/

**废弃日期：** 2026-05-20  
**废弃原因：** 客户端技术栈切换为 Android Native Client (Kotlin + Jetpack Compose + Material 3)

## 变更说明

根据 `1.txt` 最新交付约束和 `OMNICART_AGENT_COMPLETE_BLUEPRINT.md` v5.0 第 2.2 节：

- Web 前端 / Next.js / React / TailwindCSS 不再作为主线交付端
- WebView、React Native、Expo、Flutter 等跨平台方案同样废弃
- 本目录保留仅供历史参考，不再新增或维护任何代码
- 新客户端代码位于 `android-client/`

## 新主交付端

```
Android Native Client (Kotlin + Jetpack Compose + Material 3)
  + FastAPI Agent Runtime Backend
```

## 相关文档

- `docs/OMNICART_AGENT_COMPLETE_BLUEPRINT.md` — 第 2.2 节 V1 不做主线的能力
- `docs/DEVELOPMENT_DIRECTORY_STRUCTURE.md` — 第 4 节 V0-Android 最小可运行目录
- `1.txt` — 最新客户端交付约束
