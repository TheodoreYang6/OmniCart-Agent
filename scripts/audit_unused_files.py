#!/usr/bin/env python
"""P2-1: 目录清理预检脚本 — 只读扫描，输出候选清理清单，不删除任何文件。

扫描:
1. backend/app/ 下 .py 文件的静态引用数
2. frontend/.next 构建产物大小
3. __pycache__ 目录分布

输出: JSON 清单 {path, size_kb, static_refs, suggestion}
"""

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "backend" / "app"
SRC_GLOB = "**/*.py"

# 已知主链路文件 — 即使引用为0也标记为保留
CORE_FILES = {
    "main.py", "config.py", "database.py",
    "router_agent.py", "visual_agent.py", "retrieval_agent.py",
    "decision_agent.py", "response_agent.py",
    "scoring.py", "evidence_metrics.py",
    "text_retriever.py", "semantic_retriever.py",
    "response_guard.py", "evidence_checker.py",
    "memory_service.py", "memory_retriever.py", "memory_harness.py",
    "memory_extractor.py", "memory_write_policy.py",
    "context_builder.py", "conversation_service.py",
    "preference_memory.py", "long_term.py",
    "workflow.yaml",
}

# 明确标记为弱接入/未接入的模块
WEAK_MODULES = {
    "evidence_graph.py": "未接入主 workflow, 与 Android Evidence Graph 概念相似",
    "category_index.py": "未接入主链路, 可能是旧索引实验",
    "decision_harness.py": "Harness 体系重复, 主链路用 response_guard + memory_harness",
    "visual_grounding.py": "VisualAgent 另有实现, 未接入主 workflow",
    "multimodal_fallback.py": "未接入主链路, 可能过时",
    "dispatcher.py": "A2A-lite dispatcher, 主 workflow 未使用, 比赛概念实现",
    "manager.py": "ToolManager, 主链路加购直接走 API 不经此, 展示与调用不一致",
}


def scan_py_files() -> list[dict]:
    """扫描 backend/app/ 下所有 .py 文件，检查引用情况。"""
    all_files = list(APP_DIR.glob(SRC_GLOB))
    all_content = {}

    # 索引所有文件内容
    for f in all_files:
        try:
            all_content[f] = f.read_text(encoding="utf-8")
        except Exception:
            all_content[f] = ""

    results = []
    for f in sorted(all_files):
        rel = str(f.relative_to(APP_DIR)).replace("\\", "/")
        content = all_content[f]
        size_kb = round(f.stat().st_size / 1024, 1)

        # 统计静态引用: grep 整个 backend/ 查找 import/from 引用此文件名
        fname_no_ext = f.stem
        ref_count = 0
        ref_files = []
        for other_f, other_content in all_content.items():
            if other_f == f:
                continue
            # 匹配: from ... import Xxx 或 import ... Xxx
            if re.search(rf'\b{re.escape(fname_no_ext)}\b', other_content):
                ref_count += 1
                ref_files.append(str(other_f.relative_to(APP_DIR)).replace("\\", "/"))

        suggestion = ""
        if fname_no_ext + ".py" in WEAK_MODULES:
            suggestion = WEAK_MODULES[fname_no_ext + ".py"]
        elif fname_no_ext + ".py" in CORE_FILES:
            suggestion = "主链路核心文件"
        elif ref_count == 0:
            suggestion = "候选归档（静态引用=0）"

        results.append({
            "path": f"backend/app/{rel}",
            "size_kb": size_kb,
            "static_refs": ref_count,
            "ref_files": ref_files[:5],
            "suggestion": suggestion,
        })

    return results


def scan_frontend() -> dict:
    """检查 frontend/.next 产物。"""
    next_dir = ROOT / "frontend" / ".next"
    if not next_dir.exists():
        return {"exists": False, "path": "frontend/.next"}

    total_size = sum(f.stat().st_size for f in next_dir.rglob("*") if f.is_file())
    file_count = sum(1 for f in next_dir.rglob("*") if f.is_file())
    return {
        "exists": True,
        "path": "frontend/.next",
        "size_mb": round(total_size / 1024 / 1024, 1),
        "file_count": file_count,
        "suggestion": "候选清理构建产物，主前端已迁 Android",
    }


def scan_pycache() -> list[dict]:
    """检查 __pycache__ 分布。"""
    results = []
    for pycache in sorted(ROOT.rglob("__pycache__")):
        size = sum(f.stat().st_size for f in pycache.rglob("*.pyc") if f.is_file())
        count = sum(1 for _ in pycache.rglob("*.pyc"))
        results.append({
            "path": str(pycache.relative_to(ROOT)).replace("\\", "/"),
            "size_kb": round(size / 1024, 1),
            "file_count": count,
        })
    return results


def main():
    print("=" * 60)
    print("OmniCart 目录清理预检 — 只读扫描，不删除任何文件")
    print("=" * 60)

    # 1. Python 文件引用分析
    print("\n## 1. backend/app/ 文件引用分析\n")
    py_files = scan_py_files()
    zero_refs = [f for f in py_files if f["static_refs"] == 0]
    weak = [f for f in py_files if f["static_refs"] > 0 and "候选" not in f["suggestion"]]

    print(f"{'路径':<55} {'大小':>7} {'引用':>5}  建议")
    print("-" * 95)
    for f in py_files:
        if f["static_refs"] == 0 or f["suggestion"].startswith("候选") or f["suggestion"] in WEAK_MODULES.values():
            print(f"{f['path']:<55} {f['size_kb']:>6}KB {f['static_refs']:>5}  {f['suggestion']}")

    print(f"\n总文件数: {len(py_files)}")
    print(f"零引用文件: {len(zero_refs)}")
    print(f"弱接入/未接入: {len([f for f in py_files if f['suggestion'] in WEAK_MODULES.values()])}")

    # 2. frontend 产物
    print("\n## 2. frontend/.next 构建产物\n")
    fe = scan_frontend()
    if fe.get("exists"):
        print(f"  路径: {fe['path']}")
        print(f"  大小: {fe['size_mb']} MB")
        print(f"  文件数: {fe['file_count']}")
        print(f"  建议: {fe['suggestion']}")
    else:
        print(f"  不存在: {fe['path']}")

    # 3. __pycache__
    print("\n## 3. __pycache__ 分布\n")
    caches = scan_pycache()
    total_cache_kb = sum(c["size_kb"] for c in caches)
    total_cache_files = sum(c["file_count"] for c in caches)
    print(f"  __pycache__ 目录数: {len(caches)}")
    print(f"  总大小: {total_cache_kb:.0f} KB")
    print(f"  .pyc 文件数: {total_cache_files}")
    if caches:
        print(f"  建议: 已在 .gitignore 中, 无需额外处理")

    # 4. 输出 JSON
    output = {
        "py_files_summary": {
            "total": len(py_files),
            "zero_refs": len(zero_refs),
            "weak_modules": len([f for f in py_files if f["suggestion"] in WEAK_MODULES.values()]),
        },
        "zero_ref_files": [f["path"] for f in zero_refs if f["path"].split("/")[-1] not in CORE_FILES],
        "weak_modules": [f for f in py_files if f["suggestion"] in WEAK_MODULES.values()],
        "frontend": fe,
        "pycache": {"dirs": len(caches), "total_kb": round(total_cache_kb, 1), "files": total_cache_files},
    }

    json_path = ROOT / "data" / "audit_output.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n详细结果已写入: {json_path}")

    print("\n" + "=" * 60)
    print("扫描完成 — 未删除任何文件")
    print("=" * 60)


if __name__ == "__main__":
    main()
