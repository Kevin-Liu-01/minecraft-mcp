"""Demo: World Memory — save locations, resources, recall across sessions."""

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
        print("=== World Memory Demo ===\n")

        # 1. Remember spawn location
        result = await client.call_tool(
            "remember_location",
            {
                "name": "spawn",
                "x": 0,
                "y": 64,
                "z": 0,
                "tags": "spawn,home",
                "notes": "World spawn point",
            },
        )
        print(f"1. Saved spawn:\n{_text(result)}\n")

        # 2. Remember a cave with iron
        result = await client.call_tool(
            "remember_location",
            {
                "name": "iron_cave",
                "x": 120,
                "y": 32,
                "z": -50,
                "tags": "resource,cave,iron",
                "notes": "Large cave with visible iron ore",
            },
        )
        print(f"2. Saved iron cave:\n{_text(result)}\n")

        # 3. Save a resource deposit
        result = await client.call_tool(
            "remember_resource",
            {
                "block_name": "iron_ore",
                "x": 122,
                "y": 30,
                "z": -48,
                "estimated_count": 12,
            },
        )
        print(f"3. Saved iron deposit:\n{_text(result)}\n")

        result = await client.call_tool(
            "remember_resource",
            {
                "block_name": "diamond_ore",
                "x": 45,
                "y": 11,
                "z": 200,
                "estimated_count": 4,
            },
        )
        print(f"   Saved diamond deposit:\n{_text(result)}\n")

        # 4. Recall locations by tag
        result = await client.call_tool("recall_locations", {"tag": "resource"})
        print(f"4. Resource locations:\n{_text(result)}\n")

        # 5. Find nearest location
        result = await client.call_tool(
            "find_nearest_location",
            {"x": 100, "y": 64, "z": -30, "tag": ""},
        )
        print(f"5. Nearest location to (100, 64, -30):\n{_text(result)}\n")

        # 6. Find resource deposits
        result = await client.call_tool("find_resource", {"block_name": "iron_ore"})
        print(f"6. Iron ore deposits:\n{_text(result)}\n")

        # 7. Overall memory summary
        result = await client.call_tool("get_memory_summary", {})
        print(f"7. Memory summary:\n{_text(result)}\n")

        # 8. Session summary
        result = await client.call_tool("get_session_summary", {})
        print(f"8. Session summary:\n{_text(result)}\n")

        print("=== Memory Demo Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
