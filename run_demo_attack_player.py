#!/usr/bin/env -S uv run python
"""Demo: find another player and attack them until they're dead (entity gone)."""
from __future__ import annotations

import asyncio
import json
import logging
import os

from dedalus_mcp.client import MCPClient

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)

MCP_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")
MAX_ATTACKS = 120  # safety limit


def _first_text(result) -> str | None:
    for c in result.content:
        if c.type == "text":
            return c.text
    return None


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
        bot_username = data.get("username") or ""
        entities = data.get("entities") or []
        # Find another player (kind "player"; bot is not in this list)
        other_player = None
        for e in entities:
            if e.get("kind") == "player":
                other_player = e
                break
        if not other_player:
            print("No other player in range. Have another player join the world and stand near the bot.")
            return
        target_name = other_player.get("name") or "player"
        print(f"Bot '{bot_username}' will attack player '{target_name}' until they're dead...")

        attacks = 0
        while attacks < MAX_ATTACKS:
            result = await client.call_tool("attack_entity", {"name": target_name, "count": 1})
            text = _first_text(result)
            if not text:
                break
            try:
                out = json.loads(text)
                defeated = out.get("defeated", 0)
                attacks += defeated
                if defeated == 0:
                    break
                print(f"  Attack #{attacks}: defeated={defeated}")
            except json.JSONDecodeError:
                # Error message?
                if "No entity named" in (text or ""):
                    print("  Target no longer found (dead or left).")
                    break
                print("  Response:", text[:200])
                break

        # Check if they're gone
        result = await client.call_tool("get_bot_status", {})
        text = _first_text(result)
        if text:
            data = json.loads(text)
            still_there = any(
                e.get("kind") == "player" and (e.get("name") or "") == target_name
                for e in (data.get("entities") or [])
            )
            if not still_there:
                print(f"Done. '{target_name}' is dead (or left). Total attacks: {attacks}.")
            else:
                print(f"Stopped after {attacks} attacks. '{target_name}' may still be alive (max iterations reached).")
        else:
            print(f"Stopped after {attacks} attacks.")


if __name__ == "__main__":
    asyncio.run(main())
