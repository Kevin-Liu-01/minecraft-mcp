from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from enum import Enum

from dotenv import load_dotenv

from dedalus_labs import AsyncDedalus, DedalusRunner
from dedalus_mcp.client import MCPClient

from minecraft_dedalus_mcp import event_log
from minecraft_dedalus_mcp.agent.cancellation import (
    AgentCancelled,
    CancellationToken,
)


class AgentStatus(Enum):
    """Outcome of an agent run."""
    COMPLETED = "completed"
    MAX_STEPS = "max_steps"
    NO_RESPONSE = "no_response"
    CANCELLED = "cancelled"

load_dotenv()

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)


def _is_local_mcp_url(url: str) -> bool:
    return "127.0.0.1" in url or "localhost" in url


def _mcp_tools_to_openai_schemas(list_tools_result) -> list[dict]:
    """Convert MCP ListToolsResult to OpenAI-style tool schemas for the API."""
    schemas = []
    for tool in list_tools_result.tools:
        params = getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}}
        schemas.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": getattr(tool, "description", None) or f"Call {tool.name}",
                "parameters": params,
            },
        })
    return schemas


def _format_tool_args(name: str, args: dict) -> str:
    """Return a concise human-readable summary of a tool call and its arguments."""
    if not args:
        return name
    key_args = {k: v for k, v in args.items() if v is not None and v != ""}
    if not key_args:
        return name
    parts = ", ".join(f"{k}={v}" for k, v in key_args.items())
    return f"{name}({parts})"


def _format_tool_result(name: str, result_text: str, ok: bool) -> str:
    """Return a concise human-readable summary of a tool result."""
    if not ok:
        return f"  FAIL {name}: {result_text[:120]}"
    try:
        data = json.loads(result_text)
    except (json.JSONDecodeError, TypeError):
        return f"  OK {name}: {result_text[:120]}"
    action = data.get("action", name)
    pieces = []
    for key in ("collected", "mined", "placed", "crafted", "smelted", "attacked", "damage"):
        if key in data:
            pieces.append(f"{key}={data[key]}")
    for key in ("block", "item", "entity", "username", "target"):
        if key in data:
            pieces.append(str(data[key]))
    for key in ("x", "position"):
        if key in data:
            val = data[key]
            if isinstance(val, dict):
                pieces.append(f"pos=({val.get('x','?')},{val.get('y','?')},{val.get('z','?')})")
            elif key == "x" and "y" in data and "z" in data:
                pieces.append(f"pos=({data['x']},{data['y']},{data['z']})")
    if "inventory" in data and isinstance(data["inventory"], list):
        items = [f"{i.get('count','')}x{i.get('item','?')}" for i in data["inventory"][:3]]
        if items:
            pieces.append(f"inv=[{', '.join(items)}]")
    summary = ", ".join(pieces) if pieces else result_text[:80]
    return f"  OK {action}: {summary}"


_MOVEMENT_TOOLS_SKIP = {
    "go_to_known_location", "go_to_player", "go_to_entity",
}

_SEQUENTIAL_TOOLS = {
    "mine_resource", "attack_entity", "collect_items",
    "mount_entity", "interact_entity",
    "place_block", "dig_block", "build_quick",
    "hunt", "gather_wood", "clear_area",
    "follow_player", "defend_area",
    "store_items", "retrieve_items",
    "plant_crops", "harvest_crops",
    "make_tools", "smelt_all",
}


async def _execute_tool_calls_smart(
    mcp_client: MCPClient,
    tool_calls: list[dict],
    verbose: bool,
    cancel_token: CancellationToken | None = None,
) -> list[dict]:
    """Execute tool calls with smart scheduling.

    - Movement tools: only the first runs, extras get skipped (pathfinder conflict).
    - Sequential tools (place_block, dig_block): run one at a time in order (bridge mutex queues them).
    - Everything else: runs in parallel.
    - If *cancel_token* fires, remaining calls are skipped.
    """
    if len(tool_calls) <= 1:
        return [await _execute_tool_call(mcp_client, tool_calls[0], verbose, cancel_token)] if tool_calls else []

    skip_movement: list[dict] = []
    sequential: list[dict] = []
    parallel: list[dict] = []
    for tc in tool_calls:
        fn_name = tc["function"]["name"]
        if fn_name in _MOVEMENT_TOOLS_SKIP:
            skip_movement.append(tc)
        elif fn_name in _SEQUENTIAL_TOOLS:
            sequential.append(tc)
        else:
            parallel.append(tc)

    results: list[dict] = []

    if parallel:
        if cancel_token:
            cancel_token.check()
        results.extend(await asyncio.gather(
            *[_execute_tool_call(mcp_client, tc, verbose, cancel_token) for tc in parallel]
        ))

    if skip_movement:
        if cancel_token:
            cancel_token.check()
        first = skip_movement[0]
        results.append(await _execute_tool_call(mcp_client, first, verbose, cancel_token))
        for skipped in skip_movement[1:]:
            skip_msg = (
                f"Skipped: only one movement tool can run at a time. "
                f"'{first['function']['name']}' already executed this step. "
                f"Call this tool again next step if still needed."
            )
            if verbose:
                print(f"  SKIP {skipped['function']['name']}: parallel movement not allowed")
            results.append({
                "role": "tool",
                "tool_call_id": skipped["id"],
                "content": skip_msg,
            })

    for tc in sequential:
        if cancel_token:
            cancel_token.check()
        results.append(await _execute_tool_call(mcp_client, tc, verbose, cancel_token))

    return results


async def _execute_tool_call(
    mcp_client: MCPClient,
    tc: dict,
    verbose: bool,
    cancel_token: CancellationToken | None = None,
) -> dict:
    """Execute a single tool call and return the message dict for the conversation.

    If *cancel_token* fires mid-call, the MCP call is cancelled and
    ``AgentCancelled`` propagates up the stack.
    """
    name = tc["function"]["name"]
    raw_args = tc["function"]["arguments"]
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
    except json.JSONDecodeError:
        args = {}
    event_log.emit("tool_call", tool=name, args=args)
    try:
        call_coro = mcp_client.call_tool(name, args)
        if cancel_token:
            result = await cancel_token.wrap(call_coro, timeout=120.0)
        else:
            result = await call_coro
        text_parts = [
            getattr(c, "text", str(c))
            for c in result.content
            if getattr(c, "type", None) == "text"
        ]
        result_text = "\n".join(text_parts) if text_parts else str(result)
        event_log.emit("tool_result", tool=name, result=result_text[:300], ok=True)
        ok = True
    except AgentCancelled:
        raise
    except Exception as e:
        result_text = f"Error: {e}"
        event_log.emit("tool_result", tool=name, result=str(e)[:300], ok=False)
        ok = False
    if verbose:
        print(_format_tool_result(name, result_text, ok))
    return {"role": "tool", "tool_call_id": tc["id"], "content": result_text}


def _extract_tool_calls(raw_tool_calls: list) -> list[dict]:
    """Normalize LLM tool_calls into plain dicts."""
    extracted = []
    for tc in raw_tool_calls:
        tc_d = vars(tc) if hasattr(tc, "__dict__") else tc
        fn = tc_d.get("function")
        fn_d = vars(fn) if fn and hasattr(fn, "__dict__") else (fn or {})
        extracted.append({
            "id": tc_d.get("id", ""),
            "type": tc_d.get("type", "function"),
            "function": {
                "name": fn_d.get("name", ""),
                "arguments": fn_d.get("arguments", "{}"),
            },
        })
    return extracted


CORE_TOOL_NAMES: set[str] = {
    "get_bot_status", "inspect_world", "get_block_at",
    "go_to_known_location", "look_at", "jump", "set_sprint", "set_sneak", "stop_movement",
    "mine_resource", "place_block", "use_block", "craft_items", "smelt_item",
    "equip_item", "drop_item", "eat", "auto_eat",
    "attack_entity", "go_to_player", "go_to_entity", "mount_entity", "dismount", "interact_entity", "find_entities",
    "sleep", "wake", "collect_items", "fish",
    "send_chat", "read_chat", "find_players",
    # Autonomous tools
    "hunt", "gather_wood", "clear_area", "follow_player", "defend_area",
    "store_items", "retrieve_items", "plant_crops", "harvest_crops",
    "make_tools", "smelt_all",
    # Building
    "build_quick",
    "set_mode", "get_mode",
    "run_command", "teleport", "give_item", "fill_blocks",
    "set_time", "set_weather", "summon_entity", "kill_entities",
}


async def _fetch_initial_context(mcp_client: MCPClient) -> str:
    """Fetch bot status and nearby world info to prepend to the first message."""
    parts = []
    try:
        status_result = await mcp_client.call_tool("get_bot_status", {})
        status_text = "\n".join(
            getattr(c, "text", str(c))
            for c in status_result.content
            if getattr(c, "type", None) == "text"
        )
        parts.append(f"## Current bot status\n{status_text}")
    except Exception:
        pass
    try:
        world_result = await mcp_client.call_tool("inspect_world", {"radius": 16})
        world_text = "\n".join(
            getattr(c, "text", str(c))
            for c in world_result.content
            if getattr(c, "type", None) == "text"
        )
        parts.append(f"## Nearby world\n{world_text}")
    except Exception:
        pass
    return "\n\n".join(parts)


def _to_cancel_token(cancel_event: asyncio.Event | CancellationToken | None) -> CancellationToken | None:
    """Normalise a raw ``asyncio.Event`` or ``CancellationToken`` into the latter."""
    if cancel_event is None:
        return None
    if isinstance(cancel_event, CancellationToken):
        return cancel_event
    token = CancellationToken()
    token._event = cancel_event  # share the same underlying event
    return token


_LLM_CALL_TIMEOUT = 90.0  # seconds — hard cap per LLM call
_MCP_DRAIN_DELAY = 0.5  # seconds to let in-flight MCP responses finish before disconnecting


async def _run_agent_local(
    server_url: str,
    model: str,
    goal: str,
    *,
    max_steps: int = 0,
    verbose: bool = True,
    cancel_event: asyncio.Event | CancellationToken | None = None,
    tool_filter: set[str] | None = None,
) -> AgentStatus:
    """Run the agent with tool execution against the local MCP server.

    Uses a single persistent MCP connection for the entire run and executes
    tool calls in parallel when the LLM returns multiple calls per step.

    If *cancel_event* is provided and becomes set, the current LLM call or
    tool execution is interrupted immediately and ``AgentCancelled`` is raised.
    If *tool_filter* is provided, only tools whose names are in the set are exposed.
    Returns an AgentStatus indicating how the run ended.
    """
    api_key = os.getenv("DEDALUS_API_KEY")
    if not api_key:
        raise SystemExit("DEDALUS_API_KEY is required.")

    token = _to_cancel_token(cancel_event)

    async with await MCPClient.connect(server_url) as mcp_client:
        try:
            context = await _fetch_initial_context(mcp_client)

            list_result = await mcp_client.list_tools()
            all_schemas = _mcp_tools_to_openai_schemas(list_result)
            if tool_filter:
                tool_schemas = [s for s in all_schemas if s["function"]["name"] in tool_filter]
            else:
                tool_schemas = all_schemas
            if verbose:
                print(f"[local-agent] Loaded {len(tool_schemas)}/{len(all_schemas)} tools")
            event_log.emit("agent_start", goal=goal[:200], tools_loaded=len(tool_schemas))

            user_content = f"{context}\n\n---\n\n{goal}" if context else goal

            llm_client = AsyncDedalus(api_key=api_key)
            messages: list[dict] = [
                {"role": "system", "content": DEFAULT_AGENT_INSTRUCTIONS},
                {"role": "user", "content": user_content},
            ]
            steps = 0
            final_text = ""
            status = AgentStatus.MAX_STEPS
            unlimited = max_steps <= 0
            step_label = "∞" if unlimited else str(max_steps)

            while unlimited or steps < max_steps:
                if token:
                    token.check()

                steps += 1
                if verbose:
                    print(f"\n--- Step {steps}/{step_label} ---")
                event_log.emit("agent_step", step=steps, max_steps=max_steps)

                llm_coro = llm_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=tool_schemas,
                )
                if token:
                    response = await token.wrap(llm_coro, timeout=_LLM_CALL_TIMEOUT)
                else:
                    response = await llm_coro

                if not getattr(response, "choices", None) or not response.choices:
                    event_log.emit("agent_no_response")
                    status = AgentStatus.NO_RESPONSE
                    break

                choice = response.choices[0]
                msg = choice.message
                msg_dict = vars(msg) if hasattr(msg, "__dict__") else msg
                tool_calls = msg_dict.get("tool_calls") or []
                content = (getattr(msg, "content", None) or msg_dict.get("content") or "").strip()

                if content:
                    event_log.emit("llm_message", content=content[:500])

                if not tool_calls:
                    final_text = content or ""
                    if verbose and final_text:
                        print(f"  Result: {final_text[:200]}")
                    event_log.emit("agent_done", message=final_text[:500], steps=steps)
                    status = AgentStatus.COMPLETED
                    break

                if content and verbose:
                    print(f"  Thinking: {content[:120]}")

                extracted = _extract_tool_calls(tool_calls)
                if verbose:
                    previews = []
                    for tc in extracted:
                        fn_name = tc["function"]["name"]
                        try:
                            fn_args = json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"]
                        except (json.JSONDecodeError, TypeError):
                            fn_args = {}
                        previews.append(_format_tool_args(fn_name, fn_args))
                    print(f"  Calling: {', '.join(previews)}")
                event_log.emit("tool_calls", tools=[t["function"]["name"] for t in extracted])

                messages.append({"role": "assistant", "content": content or None, "tool_calls": extracted})

                if token:
                    token.check()

                tool_results = await _execute_tool_calls_smart(mcp_client, extracted, verbose, token)
                messages.extend(tool_results)

        except AgentCancelled:
            await asyncio.sleep(_MCP_DRAIN_DELAY)
            raise

    if status == AgentStatus.MAX_STEPS and verbose:
        print(f"[local-agent] Ran out of steps ({max_steps}). Task may be incomplete.")

    return status


DEFAULT_AGENT_INSTRUCTIONS = (
    "You control a Minecraft bot. Status is below — ACT IMMEDIATELY.\n"
    "Call tools. Never describe what you'd do.\n\n"

    "## Minecraft tool progression (CRITICAL — follow this order)\n"
    "Blocks require the RIGHT TOOL TIER or they drop nothing / take forever:\n"
    "  bare hands → only dirt, sand, gravel, wood\n"
    "  wooden pickaxe → stone, coal_ore\n"
    "  stone pickaxe → iron_ore, copper_ore, lapis_ore\n"
    "  iron pickaxe → gold_ore, redstone_ore, diamond_ore, emerald_ore\n"
    "  diamond pickaxe → obsidian, ancient_debris\n"
    "Axes speed up wood; shovels speed up dirt/sand/gravel.\n\n"

    "BEFORE mining a block, CHECK INVENTORY for the required tool tier.\n"
    "If you lack the tool, craft it first. The crafting chain is:\n"
    "  1. gather_wood → get logs\n"
    "  2. craft_items('oak_planks', 4) → planks from logs\n"
    "  3. craft_items('stick', 4) → sticks from planks\n"
    "  4. Place crafting_table (craft_items then place_block) — required for tools\n"
    "  5. make_tools('wooden') → wooden pickaxe+axe+sword+shovel\n"
    "  6. mine_resource('cobblestone', 12) → stone (need wooden pickaxe first!)\n"
    "  7. make_tools('stone') → upgrade to stone tools\n"
    "  8. mine_resource('iron_ore', 6) → need stone pickaxe\n"
    "  9. Smelt raw_iron → iron_ingot (needs furnace: craft_items('furnace',1) + place)\n"
    "  10. make_tools('iron') → iron tools\n"
    "NEVER skip tiers. NEVER try to mine stone/ore without a pickaxe.\n\n"

    "## Tools — each does everything in ONE call\n"
    "COMBAT: attack_entity(name?) — fights until dead. hunt(name?, count) — kill multiple mobs, collect drops.\n"
    "  defend_area(radius, duration_seconds) — guard position, kill hostiles.\n"
    "MOVEMENT: go_to_player(name), go_to_entity(name?), follow_player(name, duration_seconds).\n"
    "MINING: mine_resource(name, count), gather_wood(count, type?).\n"
    "BUILDING: build_quick(shape, material?) — "
    "pillar/tower/wall/floor/house/hut/shelter/bridge/stairs/fence/pool/farm/pyramid/arch/watchtower/ring. "
    "clear_area(radius, depth) — flatten terrain.\n"
    "CRAFTING: make_tools(material?) — auto-craft pickaxe+axe+sword+shovel. craft_items(item, count).\n"
    "SMELTING: smelt_all(item) — smelt entire stack. smelt_item(item, count).\n"
    "FARMING: plant_crops(seed, rows, cols), harvest_crops(radius).\n"
    "STORAGE: store_items(item?), retrieve_items(item, count).\n\n"

    "## Rules\n"
    "- ALWAYS check inventory before mining. If no pickaxe → craft one first.\n"
    "- Prefer high-level tools: hunt > attack_entity > manual. gather_wood > mine_resource for logs.\n"
    "- NEVER call multiple movement tools in parallel.\n"
    "- Entity/player names are in status — use them directly.\n"
    "- Do NOT send_chat status messages.\n"
    "- If a tool fails, read error and adapt.\n"
    "- Reply with SHORT summary (1 sentence) when done.\n"
)


async def run_agent(
    server_url: str,
    model: str,
    goal: str,
    *,
    max_steps: int = 0,
    verbose: bool = True,
    cancel_event: asyncio.Event | CancellationToken | None = None,
    tool_filter: set[str] | None = None,
) -> AgentStatus:
    api_key = os.getenv("DEDALUS_API_KEY")
    if not api_key:
        raise SystemExit("DEDALUS_API_KEY is required to run the Dedalus agent demo.")

    if _is_local_mcp_url(server_url):
        return await _run_agent_local(
            server_url=server_url,
            model=model,
            goal=goal,
            max_steps=max_steps,
            verbose=verbose,
            cancel_event=cancel_event,
            tool_filter=tool_filter,
        )

    client = AsyncDedalus(api_key=api_key)
    runner = DedalusRunner(client)
    result = await runner.run(
        input=goal,
        model=model,
        mcp_servers=[server_url],
        instructions=DEFAULT_AGENT_INSTRUCTIONS,
        max_steps=max_steps,
        stream=False,
        verbose=verbose,
    )
    print(result.final_output)
    return AgentStatus.COMPLETED


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Dedalus agent against the Minecraft MCP server")
    parser.add_argument("--server-url", default="http://127.0.0.1:8000/mcp")
    parser.add_argument("--model", default=os.environ.get("DEDALUS_MODEL", "openai/gpt-5-nano-mini"))
    parser.add_argument("--max-steps", type=int, default=0, help="Max agent steps (0 = unlimited)")
    parser.add_argument(
        "--goal",
        default="Join the world, inspect it, gather some wood, and build a starter pillar.",
    )
    args = parser.parse_args()
    asyncio.run(
        run_agent(
            server_url=args.server_url,
            model=args.model,
            goal=args.goal,
            max_steps=args.max_steps,
        )
    )


if __name__ == "__main__":
    main()
