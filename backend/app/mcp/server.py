"""Standard MCP Server — Model Context Protocol over stdio.

Compliant with MCP specification (JSON-RPC 2.0).
Register with Claude Desktop or any MCP client via:
  {
    "mcpServers": {
      "omnicart": {
        "command": "python",
        "args": ["-m", "app.mcp.server"],
        "cwd": "/path/to/backend"
      }
    }
  }
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# Ensure backend is on path when running as module
_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from dotenv import load_dotenv
load_dotenv(_BACKEND / ".." / ".env")  # load from project root

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationCapabilities
from mcp.server.stdio import stdio_server
from mcp.types import Tool

from app.mcp.tools import TOOL_DEFINITIONS, handle_tool

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("omnicart-mcp")

server = Server("omnicart-agent")

# ======================================================================
# Server Capabilities
# ======================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return all 8 registered shopping tools in MCP format."""
    tools = []
    for td in TOOL_DEFINITIONS:
        tools.append(Tool(
            name=td["name"],
            description=td["description"],
            inputSchema=td["inputSchema"],
        ))
    logger.info(f"Listed {len(tools)} tools")
    return tools


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list:
    """Execute a tool call and return structured content."""
    from mcp.types import TextContent

    logger.info(f"Tool call: {name}({json.dumps(arguments, ensure_ascii=False)[:200]})")
    result = await handle_tool(name, arguments)

    return [TextContent(type="text", text=result)]


# ======================================================================
# HTTP/SSE Transport (for browser MCP clients)
# ======================================================================

def create_starlette_app():
    """Create a Starlette app with SSE transport for MCP.

    Use: uvicorn app.mcp.server:create_starlette_app --port 8007
    """
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route

    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0], streams[1],
                server.create_initialization_options(),
            )

    async def health(request):
        from starlette.responses import JSONResponse
        return JSONResponse({
            "service": "omnicart-mcp",
            "version": "0.1.0",
            "tools": len(TOOL_DEFINITIONS),
        })

    app = Starlette(
        debug=False,
        routes=[
            Route("/health", health),
            Route("/sse", handle_sse),
            Mount("/messages", app=sse.handle_post_message),
        ],
    )
    return app


# ======================================================================
# Entry Point
# ======================================================================

async def run_stdio():
    """Run MCP server over stdio (for Claude Desktop integration)."""
    logger.info("OmniCart MCP Server starting (stdio mode)")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationCapabilities(
                sampling={},
                experimental={},
                roots={},
            ),
            notification_options=NotificationOptions(),
        )


def main():
    """stdio entry — python -m app.mcp.server"""
    asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
