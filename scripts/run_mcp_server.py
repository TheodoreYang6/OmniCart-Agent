#!/usr/bin/env python
"""OmniCart MCP Server launcher.

Usage:
  # stdio mode (for Claude Desktop)
  python scripts/run_mcp_server.py

  # HTTP/SSE mode (for browser clients)
  python scripts/run_mcp_server.py --http --port 8007

Claude Desktop config (~/Library/Application Support/Claude/claude_desktop_config.json):
  {
    "mcpServers": {
      "omnicart": {
        "command": "D:\\app_work\\anaconda\\envs\\omnicart\\python.exe",
        "args": ["scripts/run_mcp_server.py"],
        "cwd": "C:\\Users\\61770\\Desktop\\OmniCart-Agent"
      }
    }
  }
"""

import argparse
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "backend"))


def main():
    parser = argparse.ArgumentParser(description="OmniCart MCP Server")
    parser.add_argument("--http", action="store_true", help="Run in HTTP/SSE mode")
    parser.add_argument("--port", type=int, default=8007, help="HTTP port (default: 8007)")
    args = parser.parse_args()

    if args.http:
        import uvicorn
        from app.mcp.server import create_starlette_app
        app = create_starlette_app()
        print(f"OmniCart MCP Server (HTTP/SSE) on http://127.0.0.1:{args.port}")
        print(f"Health: http://127.0.0.1:{args.port}/health")
        print(f"SSE:    http://127.0.0.1:{args.port}/sse")
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")
    else:
        from app.mcp.server import main as mcp_main
        mcp_main()


if __name__ == "__main__":
    main()
