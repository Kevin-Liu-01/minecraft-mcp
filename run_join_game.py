#!/usr/bin/env -S uv run python
"""One-off script to call join_game MCP tool. Host/port are configurable."""
from __future__ import annotations

import argparse
import asyncio
import json
import os

from dedalus_mcp.client import MCPClient


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Call join_game MCP tool.")
    p.add_argument(
        "--host",
        default=os.environ.get("MINECRAFT_HOST", "127.0.0.1"),
        help="Minecraft server host (default: MINECRAFT_HOST or 127.0.0.1)",
    )
    p.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MINECRAFT_PORT", "25565")),
        help="Minecraft server port (default: MINECRAFT_PORT or 25565)",
    )
    p.add_argument("--username", default="DedalusBot", help="Bot username")
    p.add_argument(
        "--auth",
        default="microsoft",
        choices=("microsoft", "offline"),
        help="Auth method (default: microsoft)",
    )
    p.add_argument(
        "--mcp-url",
        default=os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp"),
        help="MCP server URL (default: MCP_SERVER_URL or http://127.0.0.1:8000/mcp)",
    )
    return p.parse_args()


async def main() -> None:
    args = _parse_args()
    server_url = args.mcp_url
    async with await MCPClient.connect(server_url) as client:
        result = await client.call_tool(
            "join_game",
            {
                "host": args.host,
                "port": args.port,
                "username": args.username,
                "auth": args.auth,
            },
        )
        for content in result.content:
            if content.type == "text":
                try:
                    print(json.dumps(json.loads(content.text), indent=2))
                except json.JSONDecodeError:
                    print(content.text)


if __name__ == "__main__":
    asyncio.run(main())
