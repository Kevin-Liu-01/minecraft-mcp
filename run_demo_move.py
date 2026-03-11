#!/usr/bin/env -S uv run python
"""Demo: get bot position from MCP, then move the bot a few blocks (no cloud agent)."""
from __future__ import annotations

import asyncio
import json
import os

from dedalus_mcp.client import MCPClient

MCP_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")


async def main() -> None:
    print("Connecting to MCP...")
    async with await MCPClient.connect(MCP_URL) as client:
        # Get current position
        result = await client.call_tool("get_bot_status", {})
        text = _first_text(result)
        if not text:
            print("No response from get_bot_status")
            return
        data = json.loads(text)
        if not data.get("connected"):
            print("Bot is not in a game. Run run_join_game.py first (and open a world to LAN).")
            return
        pos = data["position"]
        x, y, z = pos["x"], pos["y"], pos["z"]
        print(f"Bot at ({x}, {y}, {z}). Moving 5 blocks east...")

        # Move 5 blocks in +X
        target_x, target_y, target_z = x + 5, y, z
        result = await client.call_tool(
            "go_to_known_location",
            {"x": target_x, "y": target_y, "z": target_z, "range": 2},
        )
        text = _first_text(result)
        if text:
            try:
                print("Move result:", json.dumps(json.loads(text), indent=2))
            except json.JSONDecodeError:
                print("Move result:", text)
        else:
            print("Move completed (no text in response).")
        print("Demo done. You should see the bot move in-game.")


def _first_text(result) -> str | None:
    for c in result.content:
        if c.type == "text":
            return c.text
    return None


if __name__ == "__main__":
    asyncio.run(main())
