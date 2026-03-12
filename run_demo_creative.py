"""Demo: Creative Mode — switch to creative, use god-mode commands, build freely."""

from __future__ import annotations

import asyncio
import json
import os

from dedalus_mcp.client import MCPClient

MCP_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")


def _text(result) -> str:
    for c in result.content:
        if c.type == "text":
            return c.text
    return ""


async def main() -> None:
    async with await MCPClient.connect(MCP_URL) as client:
        print("=== Creative Mode Demo ===\n")

        # 1. Check current mode
        result = await client.call_tool("get_mode", {})
        print(f"1. Current mode: {_text(result)}\n")

        # 2. Switch to creative
        result = await client.call_tool("set_mode", {"mode": "creative"})
        print(f"2. Switched mode: {_text(result)}\n")

        # 3. Teleport instantly
        result = await client.call_tool("teleport", {"x": 100, "y": 80, "z": 100})
        print(f"3. Teleported: {_text(result)}\n")

        # 4. Give items
        result = await client.call_tool("give_item", {"item": "diamond_block", "count": 64})
        print(f"4. Gave items: {_text(result)}\n")

        # 5. Fill a platform
        result = await client.call_tool(
            "fill_blocks",
            {
                "x1": 95, "y1": 79, "z1": 95,
                "x2": 105, "y2": 79, "z2": 105,
                "block": "diamond_block",
            },
        )
        print(f"5. Filled platform: {_text(result)}\n")

        # 6. Set time to day
        result = await client.call_tool("set_time", {"time_value": "day"})
        print(f"6. Set time: {_text(result)}\n")

        # 7. Set weather clear
        result = await client.call_tool("set_weather", {"weather": "clear"})
        print(f"7. Set weather: {_text(result)}\n")

        # 8. Summon some mobs
        result = await client.call_tool(
            "summon_entity",
            {"entity": "pig", "x": 100, "y": 80, "z": 102},
        )
        print(f"8. Summoned: {_text(result)}\n")

        # 9. Run a raw command
        result = await client.call_tool(
            "run_command",
            {"command": "/effect give @s minecraft:speed 60 2"},
        )
        print(f"9. Raw command: {_text(result)}\n")

        # 10. Build something huge with freeform builder (still works in creative)
        result = await client.call_tool(
            "build_from_description",
            {
                "description": "a massive 15x15x8 house",
                "origin_x": 110, "origin_y": 80, "origin_z": 110,
                "material": "quartz_block",
            },
        )
        data = json.loads(_text(result))
        print(f"10. Freeform build: '{data.get('blueprint')}' — {data.get('blocks_placed', 0)} blocks\n")

        # 11. Switch back to survival
        result = await client.call_tool("set_mode", {"mode": "survival"})
        print(f"11. Back to survival: {_text(result)}\n")

        # Confirm creative tools are locked
        result = await client.call_tool("teleport", {"x": 0, "y": 64, "z": 0})
        print(f"12. Teleport in survival (should fail): {_text(result)}\n")

        print("=== Creative Mode Demo Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
