"""
OmniCart Agent 一键启动
用法: python run.py  或  双击运行
关闭: Ctrl+C 停止服务
"""

import os
import sys
import signal
import subprocess
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_DIR / "backend"
BACKEND_HOST = os.getenv("OMNICART_HOST", "0.0.0.0")
BACKEND_PORT = os.getenv("OMNICART_PORT", "8006")

_process: subprocess.Popen | None = None


def cleanup(signum=None, frame=None):
    global _process
    if _process and _process.poll() is None:
        print("\n正在停止服务...")
        _process.terminate()
        try:
            _process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _process.kill()
        print("已停止")
    sys.exit(0)


def main():
    global _process

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print("╔════════════════════════════════════════════════╗")
    print("║     OmniCart Agent V0 · 一键启动               ║")
    print("╠════════════════════════════════════════════════╣")
    print("║                                                ║")

    _process = subprocess.Popen(
        [
            sys.executable,
            "-m", "uvicorn", "app.main:app",
            "--host", BACKEND_HOST,
            "--port", BACKEND_PORT,
            "--log-level", "info",
        ],
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    import threading

    def _read():
        for line in iter(_process.stdout.readline, ""):
            if line:
                try:
                    print(f"  {line.rstrip()}")
                except UnicodeEncodeError:
                    pass

    threading.Thread(target=_read, daemon=True).start()

    time.sleep(2)

    if _process.poll() is not None:
        print("║                                                ║")
        print("║  ! 后端启动失败，请检查错误信息                 ║")
        print("╚════════════════════════════════════════════════╝")
        sys.exit(1)

    print("║                                                ║")
    print(f"║  API:  http://{BACKEND_HOST}:{BACKEND_PORT}/api/health           ║")
    print(f"║        http://{BACKEND_HOST}:{BACKEND_PORT}/api/recommend        ║")
    print("║                                                ║")
    print("║  按 Ctrl+C 停止                                 ║")
    print("╚════════════════════════════════════════════════╝")

    try:
        while _process.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
