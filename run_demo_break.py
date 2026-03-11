#!/usr/bin/env -S uv run python
"""Demo: find a nearby block and break it with dig_block."""
from __future__ import annotations

import asyncio
import json
import os

from dedalus_mcp.client import MCPClient

MCP_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")

# Prefer breaking these (avoid bedrock, etc.)
DIGGABLE = {"grass_block", "dirt", "stone", "cobblestone", "oak_log", "oak_leaves", "sand", "gravel", "grass", "tall_grass"}


async def main() -> None:
    print("Connecting to MCP...")
    async with await MCPClient.connect(MCP_URL) as client:
        result = await client.call_tool("get_bot_status", {})
        text = _first_text(result)
        if not text:
            print("No response from get_bot_status")
            return
        data = json.loads(text)
        if not data.get("connected"):
            print("Bot is not in a game. Run run_join_game.py first.")
            return
        pos = data["position"]
        print(f"Bot at ({pos['x']}, {pos['y']}, {pos['z']}). Inspecting nearby blocks...")

        result = await client.call_tool("inspect_world", {"radius": 6})
        text = _first_text(result)
        if not text:
            print("No response from inspect_world")
            return
        world = json.loads(text)
        blocks = world.get("visible_blocks", [])

        target = None
        for b in blocks:
            name = (b.get("name") or "").replace("minecraft:", "")
            if name in DIGGABLE or (name and name != "air" and "bedrock" not in name):
                target = b
                break
        if not target:
            # Fallback: try block in front and block below
            x, y, z = pos["x"], pos["y"], pos["z"]
            for dx, dy, dz in [(1, 0, 0), (0, -1, 0), (0, 0, 1), (-1, 0, 0)]:
                target = {"x": x + dx, "y": y + dy, "z": z + dz}
                break
            if not target:
                target = {"x": pos["x"] + 1, "y": pos["y"], "z": pos["z"]}

        bx, by, bz = target["x"], target["y"], target["z"]
        print(f"Breaking block at ({bx}, {by}, {bz})...")

        result = await client.call_tool("dig_block", {"x": bx, "y": by, "z": bz})
        text = _first_text(result)
        if text:
            try:
                out = json.loads(text)
                print("Result:", json.dumps(out, indent=2))
            except json.JSONDecodeError:
                print("Result:", text)
        else:
            print("Break completed.")
        print("Demo done. You should see the bot break a block in-game.")


def _first_text(result) -> str | None:
    for c in result.content:
        if c.type == "text":
            return c.text
    return None


if __name__ == "__main__":
    asyncio.run(main())
