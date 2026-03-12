"""Demo: Full Agent Workflow — combines planning, skills, memory, building, and recovery."""

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
        print("=== Full Agent Workflow Demo ===\n")
        print("This demo shows how an agent would combine all capabilities.\n")

        # Phase 1: Plan
        print("── Phase 1: Create a survival plan ──")
        result = await client.call_tool("create_plan", {"goal": "get stone tools"})
        plan = json.loads(_text(result))
        plan_id = plan["plan_id"]
        print(f"Plan '{plan_id}' created with {plan['total_steps']} steps")
        for step in plan["steps"]:
            print(f"  [{step['status']}] {step['description']}")
        print()

        # Phase 2: Execute steps with recovery
        print("── Phase 2: Execute plan steps ──")
        for i in range(min(3, plan["total_steps"])):
            step_result = await client.call_tool("get_next_plan_step", {"plan_id": plan_id})
            step = json.loads(_text(step_result))
            if "status" in step and step.get("status") == "all_steps_done":
                break
            sid = step["step_id"]
            print(f"  Executing: {step['description']}")
            print(f"    Tool: {step['tool_name']}({step['tool_args']})")

            try:
                exec_result = await client.call_tool(
                    "execute_with_recovery",
                    {
                        "tool_name": step["tool_name"],
                        "tool_args": json.dumps(step["tool_args"]),
                    },
                )
                exec_data = json.loads(_text(exec_result))
                if exec_data.get("result"):
                    await client.call_tool(
                        "complete_plan_step",
                        {
                            "plan_id": plan_id,
                            "step_id": sid,
                            "result": json.dumps(exec_data["result"]) if isinstance(exec_data["result"], dict) else str(exec_data["result"]),
                        },
                    )
                    print(f"    -> Completed (attempts: {exec_data.get('attempts', 1)})")
                else:
                    await client.call_tool(
                        "fail_plan_step",
                        {
                            "plan_id": plan_id,
                            "step_id": sid,
                            "error": exec_data.get("error", "unknown"),
                        },
                    )
                    print(f"    -> Failed: {exec_data.get('error')}")
            except Exception as e:
                await client.call_tool(
                    "fail_plan_step",
                    {"plan_id": plan_id, "step_id": sid, "error": str(e)},
                )
                print(f"    -> Failed: {e}")
        print()

        # Phase 3: Remember what we did
        print("── Phase 3: Save to memory ──")
        await client.call_tool(
            "remember_location",
            {
                "name": "base_camp",
                "x": 0, "y": 64, "z": 0,
                "tags": "base,home",
                "notes": "Our starting base",
            },
        )
        print("  Saved base_camp location")

        await client.call_tool(
            "remember_resource",
            {
                "block_name": "cobblestone",
                "x": 5, "y": 60, "z": 5,
                "estimated_count": 50,
            },
        )
        print("  Saved cobblestone deposit")

        # Phase 4: Save the workflow as a skill
        print("\n── Phase 4: Save as reusable skill ──")
        skill_seq = json.dumps([
            {"tool": "mine_resource", "args": {"name": "oak_log", "count": 4}},
            {"tool": "craft_items", "args": {"item": "oak_planks", "count": 4}},
            {"tool": "craft_items", "args": {"item": "stick", "count": 4}},
            {"tool": "mine_resource", "args": {"name": "cobblestone", "count": 11}},
            {"tool": "craft_items", "args": {"item": "stone_pickaxe", "count": 1}},
        ])
        await client.call_tool(
            "save_skill",
            {
                "name": "early_game_setup",
                "description": "Complete early game: wood, planks, sticks, stone tools",
                "tool_sequence": skill_seq,
                "tags": "early-game,tools,essential",
            },
        )
        print("  Saved 'early_game_setup' skill")

        # Phase 5: Build something
        print("\n── Phase 5: Build a starter shelter ──")
        result = await client.call_tool(
            "build_from_description",
            {
                "description": "a 5x5x4 house",
                "origin_x": 5, "origin_y": 64, "origin_z": 5,
                "material": "cobblestone",
            },
        )
        data = json.loads(_text(result))
        print(f"  Built '{data.get('blueprint')}': {data.get('blocks_placed', 0)} blocks")

        # Final: Session summary
        print("\n── Session Summary ──")
        result = await client.call_tool("get_session_summary", {})
        summary = json.loads(_text(result))
        print(f"  Total actions: {summary.get('total', 0)}")
        print(f"  Successes: {summary.get('successes', 0)}")
        print(f"  Failures: {summary.get('failures', 0)}")
        if summary.get("tools_used"):
            print("  Most used tools:")
            for t in summary["tools_used"][:5]:
                print(f"    {t['tool']}: {t['count']}x")

        result = await client.call_tool("get_memory_summary", {})
        mem = json.loads(_text(result))
        print(f"  Memory: {mem.get('locations', 0)} locations, {mem.get('resources', 0)} resources, {mem.get('structures', 0)} structures")

        print("\n=== Full Agent Workflow Demo Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
