"""Demo: Freeform Building — describe a structure in natural language and build it."""

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
        print("=== Freeform Building Demo ===\n")

        # 1. Build a house from description
        result = await client.call_tool(
            "build_from_description",
            {
                "description": "a 7x7x5 house with a door",
                "origin_x": 10,
                "origin_y": 64,
                "origin_z": 10,
                "material": "oak_planks",
            },
        )
        data = json.loads(_text(result))
        print(f"1. Built '{data.get('blueprint')}': {data.get('blocks_placed', 0)} blocks placed")
        print(f"   Dimensions: {data.get('dimensions', {})}\n")

        # 2. Build a tower
        result = await client.call_tool(
            "build_from_description",
            {
                "description": "a tall 3x3x10 tower",
                "origin_x": 25,
                "origin_y": 64,
                "origin_z": 10,
                "material": "cobblestone",
            },
        )
        data = json.loads(_text(result))
        print(f"2. Built '{data.get('blueprint')}': {data.get('blocks_placed', 0)} blocks")
        print(f"   Dimensions: {data.get('dimensions', {})}\n")

        # 3. Build a bridge
        result = await client.call_tool(
            "build_from_description",
            {
                "description": "a 3x12 bridge over a river",
                "origin_x": 10,
                "origin_y": 65,
                "origin_z": 25,
                "material": "stone_bricks",
            },
        )
        data = json.loads(_text(result))
        print(f"3. Built '{data.get('blueprint')}': {data.get('blocks_placed', 0)} blocks\n")

        # 4. Build a farm
        result = await client.call_tool(
            "build_from_description",
            {
                "description": "a 6x6 farm with fences",
                "origin_x": -10,
                "origin_y": 64,
                "origin_z": 0,
                "material": "farmland",
            },
        )
        data = json.loads(_text(result))
        print(f"4. Built '{data.get('blueprint')}': {data.get('blocks_placed', 0)} blocks\n")

        # 5. Build a platform
        result = await client.call_tool(
            "build_from_description",
            {
                "description": "an 8x8 platform",
                "origin_x": 40,
                "origin_y": 70,
                "origin_z": 40,
                "material": "oak_planks",
            },
        )
        data = json.loads(_text(result))
        print(f"5. Built '{data.get('blueprint')}': {data.get('blocks_placed', 0)} blocks\n")

        # 6. Build stairs
        result = await client.call_tool(
            "build_from_description",
            {
                "description": "a 2x8 staircase",
                "origin_x": 50,
                "origin_y": 64,
                "origin_z": 50,
                "material": "cobblestone",
            },
        )
        data = json.loads(_text(result))
        print(f"6. Built '{data.get('blueprint')}': {data.get('blocks_placed', 0)} blocks\n")

        print("=== Freeform Building Demo Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
