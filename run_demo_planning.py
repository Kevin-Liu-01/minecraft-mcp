"""Demo: Multi-Step Planning — create a plan, inspect steps, mark progress."""

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
        print("=== Multi-Step Planning Demo ===\n")

        # 1. Create a plan for getting stone tools
        result = await client.call_tool("create_plan", {"goal": "get stone tools"})
        plan_data = json.loads(_text(result))
        plan_id = plan_data["plan_id"]
        print(f"1. Created plan '{plan_id}' for stone tools:")
        for step in plan_data["steps"]:
            print(f"   [{step['status']}] {step['description']} -> {step['tool']}")
        print()

        # 2. Get the next step
        result = await client.call_tool("get_next_plan_step", {"plan_id": plan_id})
        step_data = json.loads(_text(result))
        step_id = step_data["step_id"]
        print(f"2. Next step: {step_data['description']}")
        print(f"   Tool: {step_data['tool_name']}({step_data['tool_args']})\n")

        # 3. Mark it complete
        result = await client.call_tool(
            "complete_plan_step",
            {"plan_id": plan_id, "step_id": step_id, "result": "Gathered 4 oak logs"},
        )
        print(f"3. Completed step. Plan status:\n{_text(result)}\n")

        # 4. Get the updated status
        result = await client.call_tool("get_plan_status", {"plan_id": plan_id})
        status = json.loads(_text(result))
        print(f"4. Plan progress: {status['completed']}/{status['total_steps']} steps done\n")

        # 5. Create another plan
        result = await client.call_tool("create_plan", {"goal": "build shelter"})
        shelter_plan = json.loads(_text(result))
        print(f"5. Created shelter plan with {shelter_plan['total_steps']} steps\n")

        # 6. List all plans
        result = await client.call_tool("list_plans", {})
        print(f"6. All plans:\n{_text(result)}\n")

        print("=== Planning Demo Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
