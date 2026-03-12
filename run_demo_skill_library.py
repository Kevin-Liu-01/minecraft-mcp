"""Demo: Skill Library — save a reusable multi-step skill, find and replay it."""

from __future__ import annotations

import asyncio
import json
import os
import sys

from dedalus_mcp.client import MCPClient

MCP_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")


def _text(result) -> str:
    for c in result.content:
        if c.type == "text":
            return c.text
    return ""


async def main() -> None:
    async with await MCPClient.connect(MCP_URL) as client:
        print("=== Skill Library Demo ===\n")

        # 1. Save a "gather_wood_and_craft" skill
        skill_sequence = json.dumps([
            {"tool": "mine_resource", "args": {"name": "oak_log", "count": 4}},
            {"tool": "craft_items", "args": {"item": "oak_planks", "count": 4}},
            {"tool": "craft_items", "args": {"item": "stick", "count": 4}},
            {"tool": "craft_items", "args": {"item": "crafting_table", "count": 1}},
        ])
        result = await client.call_tool(
            "save_skill",
            {
                "name": "gather_wood_and_craft",
                "description": "Mine 4 oak logs, craft planks, sticks, and a crafting table",
                "tool_sequence": skill_sequence,
                "tags": "wood,early-game,crafting",
            },
        )
        print(f"1. Saved skill:\n{_text(result)}\n")

        # 2. Save another skill
        combat_sequence = json.dumps([
            {"tool": "inspect_world", "args": {"radius": 32}},
            {"tool": "equip_item", "args": {"item": "iron_sword", "destination": "hand"}},
            {"tool": "attack_entity", "args": {"name": "zombie", "count": 3}},
            {"tool": "collect_items", "args": {"radius": 16}},
        ])
        result = await client.call_tool(
            "save_skill",
            {
                "name": "hunt_zombies",
                "description": "Equip sword, find and kill zombies, collect drops",
                "tool_sequence": combat_sequence,
                "tags": "combat,zombie,loot",
            },
        )
        print(f"2. Saved combat skill:\n{_text(result)}\n")

        # 3. Search for skills
        result = await client.call_tool("find_skills", {"query": "wood crafting early"})
        print(f"3. Search 'wood crafting early':\n{_text(result)}\n")

        # 4. Get specific skill
        result = await client.call_tool("get_skill", {"name": "gather_wood_and_craft"})
        print(f"4. Retrieved skill:\n{_text(result)}\n")

        # 5. List all skills
        result = await client.call_tool("list_skills", {})
        print(f"5. All skills:\n{_text(result)}\n")

        # 6. Record a success
        await client.call_tool("record_skill_success", {"name": "gather_wood_and_craft"})
        print("6. Recorded success for 'gather_wood_and_craft'")

        print("\n=== Skill Library Demo Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
