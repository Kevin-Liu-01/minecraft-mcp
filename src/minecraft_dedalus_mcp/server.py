from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import time
from typing import Any

from dedalus_mcp import MCPServer, tool

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("dedalus_mcp.server").setLevel(logging.WARNING)

from .bridge_client import BridgeClient, BridgeError
from .memory import SessionHistory, WorldMemory
from .modes import CreativeActions, GameMode, ModeManager, SurvivalActions
from .planning import TaskPlanner, generate_blueprint
from .playbook import recommend_goal
from .recovery import ErrorRecovery
from .skills import SkillStore

_DEFAULT_JOIN_PORT = int(os.environ.get("MINECRAFT_PORT", "25565"))


def _dump(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _compact(payload: dict[str, Any]) -> str:
    """Format a bridge response as a compact human-readable string.

    Keeps action-specific fields as a short summary line, appends position/health,
    and caps inventory to the top 8 items by count.
    """
    parts: list[str] = []
    action = payload.get("action", "result")

    skip_keys = {"action", "position", "health", "food", "inventory", "chat_messages"}
    for k, v in payload.items():
        if k in skip_keys:
            continue
        if k == "entities" and isinstance(v, list):
            ents = [
                f"{e.get('name','?')} d={e.get('distance','?')} at({e.get('x','?')},{e.get('y','?')},{e.get('z','?')})"
                for e in v[:10]
            ]
            parts.append(f"entities=[{'; '.join(ents)}]")
        elif k == "players" and isinstance(v, list):
            ps = [
                f"{p.get('name','?')} d={p.get('distance','?')} at({p.get('x','?')},{p.get('y','?')},{p.get('z','?')})"
                for p in v[:8]
            ]
            parts.append(f"players=[{'; '.join(ps)}]")
        elif isinstance(v, dict):
            inner = ", ".join(f"{ik}={iv}" for ik, iv in v.items())
            parts.append(f"{k}=({inner})")
        elif isinstance(v, list):
            parts.append(f"{k}=[{len(v)} items]")
        else:
            parts.append(f"{k}={v}")

    summary = f"{action}: {', '.join(parts)}" if parts else action

    pos = payload.get("position")
    if isinstance(pos, dict):
        summary += f" | pos=({pos.get('x','?')},{pos.get('y','?')},{pos.get('z','?')})"

    hp = payload.get("health")
    fd = payload.get("food")
    if hp is not None or fd is not None:
        summary += f" | hp={hp} food={fd}"

    inv = payload.get("inventory")
    if isinstance(inv, list) and inv:
        top = sorted(inv, key=lambda i: i.get("count", 0), reverse=True)[:8]
        inv_str = ", ".join(f"{i.get('count',0)}x{i.get('item','?')}" for i in top)
        summary += f" | inv=[{inv_str}]"

    return summary


def _record(session: SessionHistory, tool_name: str, args: dict[str, Any], result: Any, success: bool = True, error: str | None = None, duration_ms: float = 0) -> None:
    session.record_action(tool_name, args, result=result, success=success, error=error, duration_ms=duration_ms)


def build_server(bridge: BridgeClient) -> MCPServer:
    server = MCPServer(
        "minecraft-lan-mcp",
        instructions=(
            "You control a Minecraft bot over LAN via a Mineflayer bridge. "
            "Movement (go_to_known_location, and all actions that pathfind) can break blocks in the way and place scaffolding (dirt/cobblestone) to reach the goal. "
            "Prefer inspect_world before long action chains, and use recommend_next_goal to plan survival progression. "
            "Use create_plan for multi-step goals, save_skill to record reusable tool sequences, and remember_location to mark important spots. "
            "In creative mode, use run_command for slash commands, teleport, give_item, fill_blocks. "
            "In survival mode, use smelt_item for furnace operations, and auto_eat when food is low. "
            "Use build_from_description for freeform building from natural language."
        ),
    )

    skill_store = SkillStore()
    planner = TaskPlanner()
    world_memory = WorldMemory()
    session_history = SessionHistory()
    mode_manager = ModeManager()
    recovery = ErrorRecovery()
    creative = CreativeActions(bridge)
    survival = SurvivalActions(bridge)

    # ── Connection ─────────────────────────────────────────────

    @tool(description="Connect the bot to a Minecraft LAN world or local server.")
    async def join_game(
        host: str = os.environ.get("MINECRAFT_HOST", "127.0.0.1"),
        port: int = _DEFAULT_JOIN_PORT,
        username: str = "DedalusBot",
        auth: str = "offline",
        version: str | None = None,
    ) -> str:
        try:
            result = await bridge.join_game(host=host, port=port, username=username, auth=auth, version=version)
            _record(session_history, "join_game", {"host": host, "port": port}, result.model_dump())
            return _dump(result.model_dump())
        except BridgeError as e:
            _record(session_history, "join_game", {"host": host, "port": port}, None, success=False, error=str(e))
            return _dump({"ok": False, "error": str(e)})

    @tool(description="Disconnect the bot from the active game session.")
    async def leave_game() -> str:
        result = await bridge.leave_game()
        _record(session_history, "leave_game", {}, result)
        return _dump(result)

    # ── Status & World ─────────────────────────────────────────

    @tool(description="Get the current bot status, inventory, health, and nearby entities.")
    async def get_bot_status() -> str:
        result = await bridge.get_status()
        return _dump(result.model_dump())

    @tool(description="Inspect nearby blocks, entities, and local objectives around the bot.")
    async def inspect_world(radius: int = 16) -> str:
        result = await bridge.inspect_world(radius=radius)
        return _dump(result.model_dump())

    @tool(description="Get the block name at position (x, y, z).")
    async def get_block_at(x: int, y: int, z: int) -> str:
        return _dump(await bridge.get_block_at(x=x, y=y, z=z))

    # ── Movement ───────────────────────────────────────────────

    @tool(
        description="Move to coordinates (x, y, z). Pathfinder breaks blocks and places scaffolding. range=how close (1=adjacent)."
    )
    async def go_to_known_location(
        x: int, y: int, z: int, range: int = 1, timeout_ms: int = 30000,
    ) -> str:
        t0 = time.time()
        result = await bridge.move_to(x=x, y=y, z=z, range=range, timeout_ms=timeout_ms)
        ms = (time.time() - t0) * 1000
        _record(session_history, "go_to_known_location", {"x": x, "y": y, "z": z}, result, duration_ms=ms)
        return _compact(result)

    @tool(description="Turn the bot to look at block position (x, y, z).")
    async def look_at(x: int, y: int, z: int) -> str:
        return _dump(await bridge.look_at(x=x, y=y, z=z))

    @tool(description="Make the bot jump once.")
    async def jump() -> str:
        return _dump(await bridge.jump())

    @tool(description="Set sprint on or off (faster movement).")
    async def set_sprint(sprint: bool = True) -> str:
        return _dump(await bridge.set_sprint(sprint=sprint))

    @tool(description="Set sneak/crouch on or off.")
    async def set_sneak(sneak: bool = True) -> str:
        return _dump(await bridge.set_sneak(sneak=sneak))

    @tool(description="Stop current pathfinding and movement.")
    async def stop_movement() -> str:
        return _dump(await bridge.stop_movement())

    # ── Blocks & Items ─────────────────────────────────────────

    @tool(
        description=(
            "PRIMARY mining tool — mines blocks by name (e.g. 'dirt', 'oak_log', 'cobblestone', 'iron_ore'). "
            "Auto-finds nearby blocks, auto-equips best tool, collects drops. Use this for ALL mining tasks. "
            "Do NOT use dig_block unless you need to dig at an exact coordinate."
        )
    )
    async def mine_resource(name: str, count: int = 1, max_distance: int = 32) -> str:
        t0 = time.time()
        result = await bridge.mine_resource(name=name, count=count, max_distance=max_distance)
        ms = (time.time() - t0) * 1000
        _record(session_history, "mine_resource", {"name": name, "count": count}, result, duration_ms=ms)
        return _compact(result)

    @tool(description="Dig one block at exact position (x, y, z). Requires x, y, z ints. Prefer mine_resource for mining tasks.")
    async def dig_block(x: int, y: int, z: int) -> str:
        result = await bridge.dig_block(x=x, y=y, z=z)
        _record(session_history, "dig_block", {"x": x, "y": y, "z": z}, result)
        return _compact(result)

    @tool(description="Place a block from inventory at exact position (x, y, z). Requires block name and x, y, z ints.")
    async def place_block(block: str, x: int, y: int, z: int) -> str:
        result = await bridge.place_block(block=block, x=x, y=y, z=z)
        _record(session_history, "place_block", {"block": block, "x": x, "y": y, "z": z}, result)
        return _compact(result)

    @tool(description="Use/activate a block (door, button, lever, chest, furnace) at (x, y, z).")
    async def use_block(x: int, y: int, z: int) -> str:
        return _dump(await bridge.use_block(x=x, y=y, z=z))

    @tool(description="Craft items. Needs a placed crafting_table nearby for tools/complex recipes.")
    async def craft_items(item: str, count: int = 1) -> str:
        t0 = time.time()
        result = await bridge.craft_items(item=item, count=count)
        ms = (time.time() - t0) * 1000
        _record(session_history, "craft_items", {"item": item, "count": count}, result, duration_ms=ms)
        return _compact(result)

    @tool(
        description="Smelt items in a furnace. Needs a placed furnace nearby + fuel in inventory."
    )
    async def smelt_item(item: str, count: int = 1, fuel: str = "coal") -> str:
        t0 = time.time()
        result = await bridge.smelt_item(item=item, count=count, fuel=fuel)
        ms = (time.time() - t0) * 1000
        _record(session_history, "smelt_item", {"item": item, "count": count, "fuel": fuel}, result, duration_ms=ms)
        return _compact(result)

    # ── Inventory ──────────────────────────────────────────────

    @tool(description="Equip an item from inventory. destination: hand, head, torso, legs, feet.")
    async def equip_item(item: str, destination: str = "hand") -> str:
        return _compact(await bridge.equip_item(item=item, destination=destination))

    @tool(description="Drop items from inventory onto the ground.")
    async def drop_item(item: str, count: int = 1) -> str:
        return _compact(await bridge.drop_item(item=item, count=count))

    @tool(description="Eat/consume a food item from inventory (restores hunger).")
    async def eat(item: str) -> str:
        return _compact(await bridge.eat(item=item))

    @tool(description="Automatically eat the best available food if hunger is low.")
    async def auto_eat() -> str:
        result = await survival.auto_eat()
        return _dump(result)

    # ── Entities ───────────────────────────────────────────────

    @tool(
        description=(
            "Fight a mob or player until they die. Chases and attacks repeatedly until the target is killed. "
            "If name is omitted the nearest mob is auto-targeted (excludes players). "
            "To attack a PLAYER you MUST pass their exact username as name. "
            "For mobs pass the mob type (e.g. 'zombie', 'pig', 'skeleton'). "
            "count = number of kills (default 1). Auto-equips best sword."
        )
    )
    async def attack_entity(name: str = "", count: int = 1) -> str:
        t0 = time.time()
        result = await bridge.attack_entity(name=name, count=count)
        ms = (time.time() - t0) * 1000
        _record(session_history, "attack_entity", {"name": name, "count": count}, result, duration_ms=ms)
        return _compact(result)

    @tool(
        description=(
            "Move to a player by name. Resolves their position automatically — no need to call find_players first. "
            "Use this when told to 'come to me', 'go to <player>', 'follow <player>'."
        )
    )
    async def go_to_player(name: str) -> str:
        result = await bridge.go_to_player(name=name)
        return _compact(result)

    @tool(
        description=(
            "Move to an entity (mob/animal) by name. If name is omitted, moves to the nearest mob. "
            "Use this when told to 'go to the cow', 'walk to the villager', etc."
        )
    )
    async def go_to_entity(name: str = "") -> str:
        result = await bridge.go_to_entity(name=name)
        return _compact(result)

    @tool(description="Mount an entity (horse, donkey, boat, etc.) by name.")
    async def mount_entity(name: str) -> str:
        return _dump(await bridge.mount_entity(name=name))

    @tool(description="Dismount from current vehicle or mount.")
    async def dismount() -> str:
        return _dump(await bridge.dismount())

    @tool(description="Interact with an entity (e.g. villager trade, animal feed).")
    async def interact_entity(name: str) -> str:
        return _dump(await bridge.interact_entity(name=name))

    # ── Other Actions ──────────────────────────────────────────

    @tool(description="Sleep in a bed at (x, y, z).")
    async def sleep(x: int, y: int, z: int) -> str:
        return _dump(await bridge.sleep(x=x, y=y, z=z))

    @tool(description="Wake up if the bot is sleeping.")
    async def wake() -> str:
        return _dump(await bridge.wake())

    @tool(description="Collect nearby dropped items on the ground within radius.")
    async def collect_items(radius: int = 8) -> str:
        return _compact(await bridge.collect_items(radius=radius))

    @tool(description="Start fishing (must have fishing_rod in inventory).")
    async def fish() -> str:
        return _dump(await bridge.fish())

    @tool(description="Send an in-game chat message or command.")
    async def send_chat(message: str) -> str:
        return _dump(await bridge.send_chat(message=message))

    @tool(description="Read recent in-game chat messages.")
    async def read_chat(limit: int = 20) -> str:
        return _dump(await bridge.read_chat(limit=limit))

    @tool(description="List all nearby entities (mobs, animals, players, items) sorted by distance. Use this to see what's around before attacking or interacting.")
    async def find_entities(radius: int = 32) -> str:
        return _compact(await bridge.find_entities(radius=radius))

    @tool(description="Find all players in range. Returns each player's name, coordinates (x, y, z), distance from bot, and health if available.")
    async def find_players() -> str:
        return _compact(await bridge.find_players())

    # ── Autonomous Actions (one call does everything) ─────────

    @tool(
        description=(
            "Hunt and kill mobs in ONE call. Chases, fights, collects drops, repeats for 'count' kills. "
            "Omit name to kill any nearby mob. Pass name for a specific type (e.g. 'cow', 'zombie')."
        )
    )
    async def hunt(name: str = "", count: int = 5, radius: int = 48) -> str:
        return _compact(await bridge.hunt(name=name, count=count, radius=radius))

    @tool(
        description=(
            "Chop trees and collect wood in ONE call. Auto-chops connected trunk logs. "
            "Pass type for specific wood (e.g. 'oak', 'birch') or omit for any."
        )
    )
    async def gather_wood(count: int = 16, type: str = "") -> str:
        return _compact(await bridge.gather_wood(count=count, type=type))

    @tool(
        description=(
            "Clear all blocks in an area around the bot. Radius is horizontal, depth is vertical layers. "
            "Good for flattening terrain before building."
        )
    )
    async def clear_area(radius: int = 3, depth: int = 1) -> str:
        return _compact(await bridge.clear_area(radius=radius, depth=depth))

    @tool(
        description=(
            "Follow a player continuously for N seconds. Stays within 3 blocks. "
            "Use when told 'follow me', 'come with me', 'stay close'."
        )
    )
    async def follow_player(name: str, duration_seconds: int = 30) -> str:
        return _compact(await bridge.follow_player(name=name, duration_seconds=duration_seconds))

    @tool(
        description=(
            "Defend the bot's current position for N seconds. Attacks any hostile mobs that come within radius, "
            "then returns to home position. Use for 'guard here', 'defend', 'protect'."
        )
    )
    async def defend_area(radius: int = 10, duration_seconds: int = 60) -> str:
        return _compact(await bridge.defend_area(radius=radius, duration_seconds=duration_seconds))

    @tool(
        description=(
            "Store items in a nearby chest in ONE call. Omit item to store everything. "
            "Auto-finds nearest chest if coords not given."
        )
    )
    async def store_items(item: str = "", chest_x: int | None = None, chest_y: int | None = None, chest_z: int | None = None) -> str:
        return _compact(await bridge.store_items(item=item, chest_x=chest_x, chest_y=chest_y, chest_z=chest_z))

    @tool(
        description=(
            "Retrieve items from a nearby chest in ONE call. "
            "Auto-finds nearest chest if coords not given."
        )
    )
    async def retrieve_items(item: str, count: int = 64, chest_x: int | None = None, chest_y: int | None = None, chest_z: int | None = None) -> str:
        return _compact(await bridge.retrieve_items(item=item, count=count, chest_x=chest_x, chest_y=chest_y, chest_z=chest_z))

    @tool(
        description=(
            "Plant crops on farmland near the bot. Auto-hoes dirt into farmland if bot has a hoe. "
            "Rows x cols grid. Default seed is wheat_seeds."
        )
    )
    async def plant_crops(seed: str = "wheat_seeds", rows: int = 3, cols: int = 3) -> str:
        return _compact(await bridge.plant_crops(seed=seed, rows=rows, cols=cols))

    @tool(
        description=(
            "Harvest all mature crops within radius in ONE call. Collects drops. "
            "Works with wheat, carrots, potatoes, beetroots, nether_wart."
        )
    )
    async def harvest_crops(radius: int = 6) -> str:
        return _compact(await bridge.harvest_crops(radius=radius))

    @tool(
        description=(
            "Auto-craft the best tool set from available inventory materials in ONE call. "
            "Crafts pickaxe, axe, sword, shovel. Pass material (diamond, iron, stone, wooden) or auto-detect."
        )
    )
    async def make_tools(material: str = "") -> str:
        return _compact(await bridge.make_tools(material=material))

    @tool(
        description=(
            "Smelt ALL of an item in inventory at once. Like smelt_item but processes entire stack. "
            "e.g. smelt_all('raw_iron') smelts all raw_iron into iron_ingots."
        )
    )
    async def smelt_all(item: str, fuel: str = "coal") -> str:
        return _compact(await bridge.smelt_all(item=item, fuel=fuel))

    # ── Building ───────────────────────────────────────────────

    @tool(
        description=(
            "Quick-build a structure at the bot's position in ONE call. Auto-picks material in creative. "
            "Shapes: pillar/tower, wall, floor/platform, house/cabin/cottage, hut, shelter, "
            "bridge, stairs/staircase, fence/enclosure, pool, farm, pyramid, arch, watchtower, ring/circle. "
            "Only pass dimensions that matter (height, width, length, radius). "
            "No coordinates needed — builds next to the bot."
        )
    )
    async def build_quick(
        shape: str,
        material: str = "",
        height: int | None = None,
        width: int | None = None,
        length: int | None = None,
        radius: int | None = None,
    ) -> str:
        result = await bridge.build_quick(
            shape=shape, material=material,
            height=height, width=width, length=length, radius=radius,
        )
        return _compact(result)

    @tool(description="Build a preset structure at exact coordinates. Requires preset, material, origin_x/y/z.")
    async def build_structure(
        preset: str, material: str,
        origin_x: int, origin_y: int, origin_z: int,
        width: int = 5, length: int = 5, height: int = 4,
    ) -> str:
        result = await bridge.build_structure(
            preset=preset, material=material,
            origin_x=origin_x, origin_y=origin_y, origin_z=origin_z,
            width=width, length=length, height=height,
        )
        world_memory.save_structure(
            name=f"{preset}_{material}", origin_x=origin_x, origin_y=origin_y, origin_z=origin_z,
            width=width, length=length, height=height, block_count=result.get("blocks_placed", 0),
        )
        _record(session_history, "build_structure", {"preset": preset, "material": material}, result)
        return _dump(result)

    @tool(
        description="Build a structure from natural language description. Generates a blueprint and places blocks. Supports: house, tower, wall, bridge, platform, stairs, fence, pool, farm, pillar. Include dimensions like '5x5x4' or just describe what you want."
    )
    async def build_from_description(
        description: str,
        origin_x: int, origin_y: int, origin_z: int,
        material: str = "cobblestone",
    ) -> str:
        bp = generate_blueprint(
            description=description,
            origin_x=origin_x, origin_y=origin_y, origin_z=origin_z,
            material=material,
        )
        block_dicts = [b.model_dump() for b in bp.blocks]
        result = await bridge.build_blueprint(blocks=block_dicts)
        world_memory.save_structure(
            name=bp.name, origin_x=origin_x, origin_y=origin_y, origin_z=origin_z,
            width=bp.width, length=bp.length, height=bp.height,
            block_count=result.get("blocks_placed", 0),
        )
        _record(session_history, "build_from_description", {"description": description}, result)
        return _dump({
            "blueprint": bp.name,
            "description": bp.description,
            "dimensions": {"width": bp.width, "length": bp.length, "height": bp.height},
            **result,
        })

    # ── Playbook ───────────────────────────────────────────────

    @tool(description="Recommend the next survival or building goal based on current status.")
    async def recommend_next_goal(goal: str = "beat-minecraft") -> str:
        status = await bridge.get_status()
        recommendation = recommend_goal(status, goal)
        return _dump(recommendation.model_dump())

    # ── Planning ───────────────────────────────────────────────

    @tool(
        description="Create a multi-step plan for a goal. Decomposes goals like 'gather_wood', 'get_stone_tools', 'get_iron_tools', 'build_shelter', 'hunt_food', 'explore_area', 'prepare_nether' into actionable steps with tool calls. Returns plan_id to track progress."
    )
    async def create_plan(goal: str) -> str:
        plan = planner.create_plan(goal)
        _record(session_history, "create_plan", {"goal": goal}, {"plan_id": plan.plan_id})
        return _dump(planner.to_summary(plan.plan_id))

    @tool(description="Get the current status and next step of a plan by plan_id.")
    async def get_plan_status(plan_id: str) -> str:
        summary = planner.to_summary(plan_id)
        if not summary:
            return _dump({"error": f"No plan with id {plan_id}"})
        return _dump(summary)

    @tool(description="Get the next pending step from a plan. Returns the tool_name and tool_args to execute.")
    async def get_next_plan_step(plan_id: str) -> str:
        step = planner.get_next_step(plan_id)
        if not step:
            return _dump({"plan_id": plan_id, "status": "all_steps_done"})
        return _dump(step.model_dump())

    @tool(description="Mark a plan step as completed with its result.")
    async def complete_plan_step(plan_id: str, step_id: str, result: str = "") -> str:
        planner.mark_step_complete(plan_id, step_id, result)
        return _dump(planner.to_summary(plan_id))

    @tool(description="Mark a plan step as failed with an error message.")
    async def fail_plan_step(plan_id: str, step_id: str, error: str = "") -> str:
        planner.mark_step_failed(plan_id, step_id, error)
        return _dump(planner.to_summary(plan_id))

    @tool(description="List all plans, optionally filtered by status (pending, in_progress, completed, failed).")
    async def list_plans(status: str = "") -> str:
        plans = planner.list_plans(status=status if status else None)
        return _dump([
            {"plan_id": p.plan_id, "goal": p.goal, "status": p.status, "steps": len(p.steps)}
            for p in plans
        ])

    # ── Skill Library ──────────────────────────────────────────

    @tool(
        description="Save a reusable skill (a named sequence of tool calls). Use after successfully completing a multi-tool workflow you want to remember. tool_sequence is a list of {tool, args} objects."
    )
    async def save_skill(
        name: str, description: str,
        tool_sequence: str,
        tags: str = "",
    ) -> str:
        seq = json.loads(tool_sequence) if isinstance(tool_sequence, str) else tool_sequence
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        entry = skill_store.add_skill(name, description, seq, tag_list)
        _record(session_history, "save_skill", {"name": name}, entry.model_dump())
        return _dump(entry.model_dump())

    @tool(description="Find skills matching a query. Returns matching skill names, descriptions, and tool sequences.")
    async def find_skills(query: str, limit: int = 5) -> str:
        results = skill_store.find_skills(query, limit)
        return _dump([s.model_dump() for s in results])

    @tool(description="Get a specific skill by name, including its full tool sequence.")
    async def get_skill(name: str) -> str:
        skill = skill_store.get_skill(name)
        if not skill:
            return _dump({"error": f"No skill named '{name}'"})
        return _dump(skill.model_dump())

    @tool(description="List all saved skills with their success counts.")
    async def list_skills() -> str:
        return _dump(skill_store.to_summary())

    @tool(description="Record that a skill was used successfully (improves ranking).")
    async def record_skill_success(name: str) -> str:
        skill_store.record_success(name)
        return _dump({"name": name, "recorded": True})

    @tool(description="Remove a skill from the library.")
    async def remove_skill(name: str) -> str:
        removed = skill_store.remove_skill(name)
        return _dump({"name": name, "removed": removed})

    # ── Memory ─────────────────────────────────────────────────

    @tool(
        description="Save a named location in world memory. Use to remember bases, resources, structures, or points of interest. tags=comma-separated (e.g. 'base,spawn,home')."
    )
    async def remember_location(
        name: str, x: int, y: int, z: int, tags: str = "", notes: str = "",
    ) -> str:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        loc = world_memory.save_location(name, x, y, z, tag_list, notes)
        return _dump(loc.model_dump())

    @tool(description="Recall saved locations. Optionally filter by tag (e.g. 'base', 'resource', 'structure').")
    async def recall_locations(tag: str = "") -> str:
        locs = world_memory.get_locations(tag=tag if tag else None)
        return _dump([loc.model_dump() for loc in locs])

    @tool(description="Find the nearest saved location to a position. Optionally filter by tag.")
    async def find_nearest_location(x: int, y: int, z: int, tag: str = "") -> str:
        loc = world_memory.find_nearest_location(x, y, z, tag=tag if tag else None)
        if not loc:
            return _dump({"error": "No locations saved"})
        return _dump(loc.model_dump())

    @tool(description="Save a resource deposit location in memory (e.g. iron_ore vein at coords).")
    async def remember_resource(block_name: str, x: int, y: int, z: int, estimated_count: int = 1) -> str:
        res = world_memory.save_resource(block_name, x, y, z, estimated_count)
        return _dump(res.model_dump())

    @tool(description="Find saved resource deposits by block name (e.g. 'iron_ore', 'diamond_ore').")
    async def find_resource(block_name: str) -> str:
        deposits = world_memory.find_resource(block_name)
        return _dump([d.model_dump() for d in deposits])

    @tool(description="Get a summary of everything in world memory (locations, resources, structures).")
    async def get_memory_summary() -> str:
        return _dump(world_memory.to_summary())

    @tool(description="Get the session history summary: actions taken, successes, failures, most-used tools.")
    async def get_session_summary() -> str:
        return _dump(session_history.summarize())

    @tool(description="Get recent session actions (last N tool calls with results).")
    async def get_recent_actions(limit: int = 20) -> str:
        records = session_history.get_recent(limit)
        return _dump([r.model_dump() for r in records])

    @tool(description="Get recent failures from session history for debugging.")
    async def get_recent_failures(limit: int = 10) -> str:
        records = session_history.get_failures(limit)
        return _dump([r.model_dump() for r in records])

    # ── Mode System ────────────────────────────────────────────

    @tool(
        description="Switch between 'creative' and 'survival' mode. Creative mode unlocks slash commands (teleport, give, fill, summon, time, weather). Survival mode uses normal pathfinding and resource gathering."
    )
    async def set_mode(mode: str) -> str:
        new_mode = mode_manager.set_mode(mode)
        if new_mode == GameMode.CREATIVE:
            await creative.set_gamemode("creative")
        else:
            await creative.set_gamemode("survival")
        _record(session_history, "set_mode", {"mode": mode}, {"mode": new_mode.value})
        return _dump({"mode": new_mode.value})

    @tool(description="Get the current game mode (creative or survival).")
    async def get_mode() -> str:
        return _dump({"mode": mode_manager.mode.value})

    # ── Creative Mode Tools ────────────────────────────────────

    @tool(
        description="[Creative] Run a slash command (e.g. '/give @s diamond 64', '/time set day'). Only works in creative mode."
    )
    async def run_command(command: str) -> str:
        if not mode_manager.is_creative():
            return _dump({"error": "run_command requires creative mode. Use set_mode('creative') first."})
        result = await creative.run_command(command)
        _record(session_history, "run_command", {"command": command}, result)
        return _dump(result)

    @tool(description="[Creative] Teleport the bot instantly to (x, y, z).")
    async def teleport(x: int, y: int, z: int) -> str:
        if not mode_manager.is_creative():
            return _dump({"error": "teleport requires creative mode. Use set_mode('creative') first."})
        result = await creative.teleport(x, y, z)
        _record(session_history, "teleport", {"x": x, "y": y, "z": z}, result)
        return _dump(result)

    @tool(description="[Creative] Give the bot items (e.g. 'diamond', 64).")
    async def give_item(item: str, count: int = 1) -> str:
        if not mode_manager.is_creative():
            return _dump({"error": "give_item requires creative mode. Use set_mode('creative') first."})
        result = await creative.give_item(item, count)
        _record(session_history, "give_item", {"item": item, "count": count}, result)
        return _dump(result)

    @tool(
        description="[Creative] Fill a volume of blocks from (x1,y1,z1) to (x2,y2,z2) with a block type."
    )
    async def fill_blocks(
        x1: int, y1: int, z1: int,
        x2: int, y2: int, z2: int,
        block: str,
    ) -> str:
        if not mode_manager.is_creative():
            return _dump({"error": "fill_blocks requires creative mode. Use set_mode('creative') first."})
        result = await creative.fill_blocks(x1, y1, z1, x2, y2, z2, block)
        _record(session_history, "fill_blocks", {"block": block}, result)
        return _dump(result)

    @tool(description="[Creative] Set the time of day (e.g. 'day', 'night', 'noon', '0').")
    async def set_time(time_value: str) -> str:
        if not mode_manager.is_creative():
            return _dump({"error": "set_time requires creative mode."})
        return _dump(await creative.set_time(time_value))

    @tool(description="[Creative] Set the weather (clear, rain, thunder).")
    async def set_weather(weather: str) -> str:
        if not mode_manager.is_creative():
            return _dump({"error": "set_weather requires creative mode."})
        return _dump(await creative.set_weather(weather))

    @tool(description="[Creative] Summon an entity at (x, y, z).")
    async def summon_entity(entity: str, x: int, y: int, z: int) -> str:
        if not mode_manager.is_creative():
            return _dump({"error": "summon_entity requires creative mode."})
        return _dump(await creative.summon_entity(entity, x, y, z))

    @tool(description="[Creative] Kill all non-player entities (or specify target selector).")
    async def kill_entities(target: str = "@e[type=!player]") -> str:
        if not mode_manager.is_creative():
            return _dump({"error": "kill_entities requires creative mode."})
        return _dump(await creative.kill_entities(target))

    # ── Survival Helpers ───────────────────────────────────────

    @tool(
        description="[Survival] Check if the bot has enough of an item, and get suggestions for how to acquire it if not."
    )
    async def ensure_has_item(item: str, count: int = 1) -> str:
        result = await survival.ensure_has_item(item, count)
        return _dump(result)

    @tool(
        description="[Survival] Move to a position with automatic retry on failure (tries alternative positions if stuck)."
    )
    async def safe_move_to(x: int, y: int, z: int) -> str:
        result = await survival.safe_move_to(x, y, z)
        _record(session_history, "safe_move_to", {"x": x, "y": y, "z": z}, result)
        return _dump(result)

    # ── Error Recovery ─────────────────────────────────────────

    @tool(
        description="Execute a tool call with automatic error recovery. Retries with adjusted parameters on failure (moves to alternative positions, tries alternative resources). tool_args is a JSON string."
    )
    async def execute_with_recovery(tool_name: str, tool_args: str) -> str:
        args = json.loads(tool_args) if isinstance(tool_args, str) else tool_args
        tool_fn_map: dict[str, Any] = {
            "mine_resource": lambda **kw: bridge.mine_resource(
                name=kw["name"], count=kw.get("count", 1), max_distance=kw.get("max_distance", 32),
            ),
            "go_to_known_location": lambda **kw: bridge.move_to(
                x=kw["x"], y=kw["y"], z=kw["z"],
                range=kw.get("range", 1), timeout_ms=kw.get("timeout_ms", 30000),
            ),
            "attack_entity": lambda **kw: bridge.attack_entity(
                name=kw.get("name", ""), count=kw.get("count", 1),
            ),
            "dig_block": lambda **kw: bridge.dig_block(x=kw["x"], y=kw["y"], z=kw["z"]),
            "place_block": lambda **kw: bridge.place_block(
                block=kw["block"], x=kw["x"], y=kw["y"], z=kw["z"],
            ),
            "craft_items": lambda **kw: bridge.craft_items(
                item=kw["item"], count=kw.get("count", 1),
            ),
            "smelt_item": lambda **kw: bridge.smelt_item(
                item=kw["item"], count=kw.get("count", 1), fuel=kw.get("fuel", "coal"),
            ),
        }
        fn = tool_fn_map.get(tool_name)
        if not fn:
            return _dump({"error": f"Recovery not supported for tool: {tool_name}"})
        result = await recovery.execute_with_retry(fn, tool_name, args)
        _record(
            session_history, f"recovery:{tool_name}", args, result,
            success=result.get("result") is not None,
            error=result.get("error"),
        )
        return _dump(result)

    # ── Collect all tools ──────────────────────────────────────

    server.collect(
        # Connection
        join_game, leave_game,
        # Status & World
        get_bot_status, inspect_world, get_block_at,
        # Movement
        go_to_known_location, look_at, jump, set_sprint, set_sneak, stop_movement,
        # Blocks & Items
        mine_resource, dig_block, place_block, use_block, craft_items, smelt_item,
        # Inventory
        equip_item, drop_item, eat, auto_eat,
        # Entities
        attack_entity, go_to_player, go_to_entity, mount_entity, dismount, interact_entity, find_entities,
        # Other actions
        sleep, wake, collect_items, fish, send_chat, read_chat, find_players,
        # Autonomous (one-call-does-everything)
        hunt, gather_wood, clear_area, follow_player, defend_area,
        store_items, retrieve_items, plant_crops, harvest_crops,
        make_tools, smelt_all,
        # Building
        build_quick, build_structure, build_from_description,
        # Playbook
        recommend_next_goal,
        # Planning
        create_plan, get_plan_status, get_next_plan_step,
        complete_plan_step, fail_plan_step, list_plans,
        # Skill Library
        save_skill, find_skills, get_skill, list_skills,
        record_skill_success, remove_skill,
        # Memory
        remember_location, recall_locations, find_nearest_location,
        remember_resource, find_resource, get_memory_summary,
        get_session_summary, get_recent_actions, get_recent_failures,
        # Mode System
        set_mode, get_mode,
        # Creative
        run_command, teleport, give_item, fill_blocks,
        set_time, set_weather, summon_entity, kill_entities,
        # Survival helpers
        ensure_has_item, safe_move_to,
        # Error Recovery
        execute_with_recovery,
    )
    return server


async def _run(host: str, port: int, path: str, bridge_url: str) -> None:
    bridge = BridgeClient(bridge_url)
    server = build_server(bridge)
    try:
        await server.serve(host=host, port=port, path=path)
    finally:
        await bridge.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the Minecraft Dedalus MCP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--path", default="/mcp")
    parser.add_argument("--bridge-url", default="http://127.0.0.1:8787")
    args = parser.parse_args()
    asyncio.run(_run(host=args.host, port=args.port, path=args.path, bridge_url=args.bridge_url))


if __name__ == "__main__":
    main()
