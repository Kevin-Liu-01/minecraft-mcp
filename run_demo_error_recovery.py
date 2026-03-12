"""Demo: Error Recovery — execute tools with automatic retry and alternative strategies."""

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
        print("=== Error Recovery Demo ===\n")

        # 1. Execute mining with recovery (will retry with alternatives if block not found)
        print("1. Mining oak_log with recovery wrapper...")
        result = await client.call_tool(
            "execute_with_recovery",
            {
                "tool_name": "mine_resource",
                "tool_args": json.dumps({"name": "oak_log", "count": 5, "max_distance": 32}),
            },
        )
        data = json.loads(_text(result))
        print(f"   Attempts: {data.get('attempts', '?')}")
        print(f"   Recovered: {data.get('recovered', False)}")
        print(f"   Result: {json.dumps(data.get('result'), indent=2) if data.get('result') else data.get('error')}\n")

        # 2. Try attacking an entity (recovery will try alternatives)
        print("2. Attacking 'cow' with recovery...")
        result = await client.call_tool(
            "execute_with_recovery",
            {
                "tool_name": "attack_entity",
                "tool_args": json.dumps({"name": "cow", "count": 1}),
            },
        )
        data = json.loads(_text(result))
        print(f"   Attempts: {data.get('attempts', '?')}")
        print(f"   Result: {json.dumps(data.get('result'), indent=2) if data.get('result') else data.get('error')}\n")

        # 3. Check recent failures from session
        print("3. Checking session for recent failures...")
        result = await client.call_tool("get_recent_failures", {"limit": 5})
        print(f"   Failures: {_text(result)}\n")

        # 4. Session summary showing recovery stats
        result = await client.call_tool("get_session_summary", {})
        print(f"4. Session summary:\n{_text(result)}\n")

        print("=== Error Recovery Demo Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
