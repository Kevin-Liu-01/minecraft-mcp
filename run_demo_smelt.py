"""Demo: Smelting — mine raw iron, smelt it in a furnace."""

from __future__ import annotations

import asyncio
import json
import os

from dedalus_mcp.client import MCPClient
from minecraft_dedalus_mcp.constants import SMELTABLE_ITEMS

MCP_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")


def _text(result) -> str:
    for c in result.content:
        if c.type == "text":
            return c.text
    return ""


async def main() -> None:
    async with await MCPClient.connect(MCP_URL) as client:
        print("=== Smelting Demo ===\n")

        # 1. Check status
        result = await client.call_tool("get_bot_status", {})
        status = json.loads(_text(result))
        print(f"1. Bot at {status.get('position', 'unknown')}")
        print(f"   Inventory: {status.get('inventory', [])}\n")

        # 2. Smelt raw iron (requires furnace nearby and raw_iron + fuel in inventory)
        print("2. Smelting raw_iron with coal fuel...")
        try:
            result = await client.call_tool(
                "smelt_item", {"item": "raw_iron", "count": 3, "fuel": "coal"},
            )
            print(f"   Result: {_text(result)}\n")
        except Exception as e:
            print(f"   (Expected in sim without furnace) Error: {e}\n")

        # 3. Show what's smeltable
        print("3. Smeltable items reference:")
        for raw, cooked in list(SMELTABLE_ITEMS.items())[:10]:
            print(f"   {raw} -> {cooked}")

        print("\n=== Smelting Demo Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
