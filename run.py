"""
OmniCart Agent 一键启动（后端 + 前端 + 数据库连通检查）
用法: python run.py  或  双击运行
关闭: Ctrl+C 同时停止前后端
"""

import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _configure_utf8_stdio() -> None:
    """Avoid Windows/PyCharm consoles failing on Unicode status symbols."""
    if os.name != "nt":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


_configure_utf8_stdio()

PROJECT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_DIR / "backend"
FRONTEND_DIR = PROJECT_DIR / "web-client"
BACKEND_HOST = os.getenv("OMNICART_HOST", "0.0.0.0")
BACKEND_PORT = os.getenv("OMNICART_PORT", "8006")
FRONTEND_PORT = os.getenv("OMNICART_WEB_PORT", "5173")

_procs: list[subprocess.Popen] = []

OK = "✅"
FAIL = "❌"
WARN = "⚠️ "


# ============================================================
# 数据库连通检查
# ============================================================

def _parse_host_port(url: str, default_port: int) -> tuple[str, int]:
    """从 URL 中提取 host:port（支持 postgresql+asyncpg:// / redis:// / http://）。"""
    m = re.search(r"@?([\w.\-]+):(\d+)", url or "")
    if m:
        return m.group(1), int(m.group(2))
    return "127.0.0.1", default_port


def check_postgres() -> tuple[bool, str]:
    host, port = _parse_host_port(os.getenv("DATABASE_URL", ""), 5432)
    try:
        with socket.create_connection((host, port), timeout=2):
            return True, f"{host}:{port}"
    except OSError as e:
        return False, f"{host}:{port} ({e.__class__.__name__})"


def check_redis() -> tuple[bool, str]:
    host, port = _parse_host_port(os.getenv("REDIS_URL", ""), 6379)
    try:
        with socket.create_connection((host, port), timeout=2) as s:
            s.sendall(b"PING\r\n")
            resp = s.recv(16)
            if b"PONG" in resp:
                return True, f"{host}:{port}"
            return False, f"{host}:{port} (响应异常: {resp!r})"
    except OSError as e:
        return False, f"{host}:{port} ({e.__class__.__name__})"


def check_qdrant() -> tuple[bool, str]:
    base = (os.getenv("QDRANT_URL") or "http://127.0.0.1:6333").rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/healthz", timeout=2) as r:
            if r.status == 200:
                return True, base
            return False, f"{base} (HTTP {r.status})"
    except Exception as e:
        return False, f"{base} ({e.__class__.__name__})"


def check_databases() -> bool:
    """检查三个数据库连通性并打印状态，返回是否全部可用。"""
    print("┌─ 数据库连通检查 ───────────────────────────────")
    all_ok = True
    for name, checker in [("PostgreSQL", check_postgres),
                          ("Redis     ", check_redis),
                          ("Qdrant    ", check_qdrant)]:
        ok, detail = checker()
        all_ok = all_ok and ok
        print(f"│  {OK if ok else FAIL} {name}  {detail}")
    print("└────────────────────────────────────────────────")
    return all_ok


def wait_backend_health(timeout: float = 30.0) -> dict | None:
    """轮询后端 /api/health，返回健康信息（含 DB 真实连接状态）。"""
    host = "127.0.0.1" if BACKEND_HOST == "0.0.0.0" else BACKEND_HOST
    url = f"http://{host}:{BACKEND_PORT}/api/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(0.5)
    return None


# ============================================================
# 进程管理
# ============================================================

def _spawn(cmd: list[str], cwd: Path, tag: str) -> subprocess.Popen:
    """启动子进程并用 [tag] 前缀转发其输出。"""
    proc = subprocess.Popen(
        cmd, cwd=str(cwd),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    _procs.append(proc)

    def _read():
        for line in iter(proc.stdout.readline, ""):
            if line:
                try:
                    print(f"  [{tag}] {line.rstrip()}")
                except UnicodeEncodeError:
                    pass

    threading.Thread(target=_read, daemon=True).start()
    return proc


def cleanup(signum=None, frame=None):
    alive = [p for p in _procs if p.poll() is None]
    if alive:
        print("\n正在停止前后端服务...")
        for p in alive:
            p.terminate()
        for p in alive:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        print("已全部停止")
    sys.exit(0)


# ============================================================
# 启动前清理残留进程
# ============================================================

def kill_stale_processes():
    """杀掉上次残留的前后端进程（端口占用 + 旧 uvicorn/run.py），防止启动失败。

    多实例混跑会抢占 MPS 显存、导致端口漂移，启动前统一清场。
    """
    me = os.getpid()
    stale: set[int] = set()

    # 1. 占用前后端端口的进程
    for port in (BACKEND_PORT, FRONTEND_PORT):
        try:
            out = subprocess.run(["lsof", "-ti", f":{port}"],
                                 capture_output=True, text=True, timeout=5)
            stale.update(int(p) for p in out.stdout.split() if p.strip())
        except Exception:
            pass

    # 2. 残留的后端 uvicorn / 旧 run.py 守护进程
    for pattern in ("uvicorn app.main:app", "run.py"):
        try:
            out = subprocess.run(["pgrep", "-f", pattern],
                                 capture_output=True, text=True, timeout=5)
            stale.update(int(p) for p in out.stdout.split() if p.strip())
        except Exception:
            pass

    # 排除自己与父进程，防止自杀
    stale.discard(me)
    stale.discard(os.getppid())

    if not stale:
        return
    for pid in stale:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    print(f"已清理 {len(stale)} 个残留进程: {sorted(stale)}")
    time.sleep(1)  # 等端口/MPS 释放


# ============================================================
# 主流程
# ============================================================

def main():
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print("╔════════════════════════════════════════════════╗")
    print("║   OmniCart Agent · 一键启动（前端+后端+DB检查）  ║")
    print("╚════════════════════════════════════════════════╝")

    # 0. 清理残留进程（端口占用/旧实例），防止打不开
    kill_stale_processes()

    # 1. 数据库连通检查
    if not check_databases():
        print(f"{WARN}存在不可用的数据库 — 后端将自动降级（如 JSON 模式），"
              f"如需完整功能请先启动对应服务。")

    # 2. 启动后端
    backend = _spawn(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", BACKEND_HOST, "--port", BACKEND_PORT, "--log-level", "info"],
        cwd=BACKEND_DIR, tag="后端",
    )

    # 3. 启动前端（npm run dev；node_modules 缺失时提示先安装）
    frontend = None
    if (FRONTEND_DIR / "package.json").exists():
        if (FRONTEND_DIR / "node_modules").is_dir():
            frontend = _spawn(
                ["npx.cmd" if os.name == "nt" else "npx",
                 "vite", "--port", FRONTEND_PORT],
                cwd=FRONTEND_DIR, tag="前端",
            )
        else:
            print(f"{WARN}web-client/node_modules 不存在，跳过前端。"
                  f"请先执行: cd web-client && npm install")

    # 4. 等待后端就绪并显示真实 DB 连接状态（后端视角）
    health = wait_backend_health()
    if backend.poll() is not None:
        print(f"\n{FAIL} 后端启动失败，请检查上方错误日志")
        cleanup()
    host_show = "127.0.0.1" if BACKEND_HOST == "0.0.0.0" else BACKEND_HOST

    print("┌─ 服务就绪 ─────────────────────────────────────")
    if health:
        print(f"│  {OK} 后端   http://{host_show}:{BACKEND_PORT}  "
              f"(v{health.get('version', '?')})")
        for db in ("postgres", "qdrant", "redis"):
            status = health.get(db, "unknown")
            mark = OK if status == "connected" else FAIL
            print(f"│     {mark} {db}: {status}")
    else:
        print(f"│  {WARN}后端健康检查超时，请留意日志")
    if frontend and frontend.poll() is None:
        print(f"│  {OK} 前端   http://localhost:{FRONTEND_PORT}")
    print("│")
    print("│  按 Ctrl+C 同时停止前后端")
    print("└────────────────────────────────────────────────")

    # 5. 守护：任一核心进程退出则整体退出
    try:
        while backend.poll() is None:
            time.sleep(1)
        print(f"\n{FAIL} 后端进程已退出 (code={backend.returncode})")
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
