#!/usr/bin/env -S uv run python
"""Call any MCP tool from the command line. Use after the bot has joined (run_join_game.py)."""
from __future__ import annotations

import argparse
import asyncio
import json
import os

from dedalus_mcp.client import MCPClient


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Call a Minecraft MCP tool. Bot must already be in-game (run_join_game.py first)."
    )
    p.add_argument(
        "tool",
        help="Tool name, e.g. get_bot_status, inspect_world, mine_resource, craft_items, send_chat",
    )
    p.add_argument(
        "args",
        nargs="?",
        default="{}",
        help='JSON object of tool arguments, e.g. \'{"name": "oak_log", "count": 4}\' for mine_resource',
    )
    p.add_argument(
        "--mcp-url",
        default=os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp"),
        help="MCP server URL",
    )
    return p.parse_args()


async def main() -> None:
    args = _parse_args()
    try:
        tool_args = json.loads(args.args) if isinstance(args.args, str) else args.args
    except json.JSONDecodeError as e:
        raise SystemExit(f"Invalid JSON for tool args: {e}") from e

    async with await MCPClient.connect(args.mcp_url) as client:
        result = await client.call_tool(args.tool, tool_args)
        for content in result.content:
            if content.type == "text":
                try:
                    print(json.dumps(json.loads(content.text), indent=2))
                except json.JSONDecodeError:
                    print(content.text)


if __name__ == "__main__":
    asyncio.run(main())
