from __future__ import annotations

import argparse
import asyncio
import json
import os

from dedalus_mcp import MCPServer, tool

from .bridge_client import BridgeClient, BridgeError
from .playbook import recommend_goal

_DEFAULT_JOIN_PORT = int(os.environ.get("MINECRAFT_PORT", "25565"))


def _dump(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def build_server(bridge: BridgeClient) -> MCPServer:
    server = MCPServer(
        "minecraft-lan-mcp",
        instructions=(
            "You control a Minecraft bot over LAN via a Mineflayer bridge. "
            "Movement (go_to_known_location, and all actions that pathfind) can break blocks in the way and place scaffolding (dirt/cobblestone) to reach the goal. "
            "Prefer inspect_world before long action chains, and use recommend_next_goal to plan survival progression."
        ),
    )

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
            return _dump(result.model_dump())
        except BridgeError as e:
            return _dump({"ok": False, "error": str(e)})

    @tool(description="Disconnect the bot from the active game session.")
    async def leave_game() -> str:
        result = await bridge.leave_game()
        return _dump(result)

    @tool(description="Get the current bot status, inventory, health, and nearby entities.")
    async def get_bot_status() -> str:
        result = await bridge.get_status()
        return _dump(result.model_dump())

    @tool(description="Inspect nearby blocks, entities, and local objectives around the bot.")
    async def inspect_world(radius: int = 16) -> str:
        result = await bridge.inspect_world(radius=radius)
        return _dump(result.model_dump())

    @tool(
        description="Move the bot to a target block coordinate (x, y, z). Pathfinding will break blocks in the way and place scaffolding (dirt/cobblestone) if needed. Use inspect_world or get_bot_status to get coordinates. range=1 means adjacent block; increase for 'near'. timeout_ms limits how long the bot tries (default 30000)."
    )
    async def go_to_known_location(
        x: int,
        y: int,
        z: int,
        range: int = 1,
        timeout_ms: int = 30000,
    ) -> str:
        result = await bridge.move_to(x=x, y=y, z=z, range=range, timeout_ms=timeout_ms)
        return _dump(result)

    @tool(
        description="Break and collect blocks by resource name (e.g. oak_log, cobblestone). Bot moves to and digs the blocks. Use for gathering materials. count=how many to collect; max_distance=how far to look (default 32)."
    )
    async def mine_resource(name: str, count: int = 1, max_distance: int = 32) -> str:
        result = await bridge.mine_resource(name=name, count=count, max_distance=max_distance)
        return _dump(result)

    @tool(description="Craft a named item using currently available inventory.")
    async def craft_items(item: str, count: int = 1) -> str:
        result = await bridge.craft_items(item=item, count=count)
        return _dump(result)

    @tool(
        description="Place a block from inventory at position (x, y, z). Block must be in inventory (e.g. cobblestone, oak_planks, dirt). Get coordinates from inspect_world or get_bot_status."
    )
    async def place_block(block: str, x: int, y: int, z: int) -> str:
        result = await bridge.place_block(block=block, x=x, y=y, z=z)
        return _dump(result)

    @tool(
        description="Break/dig one block at exact position (x, y, z). Use when you know the block location (e.g. from inspect_world). Bot moves to the block and digs it."
    )
    async def dig_block(x: int, y: int, z: int) -> str:
        result = await bridge.dig_block(x=x, y=y, z=z)
        return _dump(result)

    @tool(
        description="Attack nearby entity/entities by type name (e.g. zombie, skeleton, cow). Bot moves to and attacks. count=how many to attack (default 1). Use inspect_world or get_bot_status to see entity names."
    )
    async def attack_entity(name: str, count: int = 1) -> str:
        result = await bridge.attack_entity(name=name, count=count)
        return _dump(result)

    @tool(description="Send an in-game chat message or command.")
    async def send_chat(message: str) -> str:
        result = await bridge.send_chat(message=message)
        return _dump(result)

    @tool(description="Read recent in-game chat messages.")
    async def read_chat(limit: int = 20) -> str:
        result = await bridge.read_chat(limit=limit)
        return _dump(result)

    @tool(description="Build a simple preset structure such as a pillar, wall, bridge, or hut.")
    async def build_structure(
        preset: str,
        material: str,
        origin_x: int,
        origin_y: int,
        origin_z: int,
        width: int = 5,
        length: int = 5,
        height: int = 4,
    ) -> str:
        result = await bridge.build_structure(
            preset=preset,
            material=material,
            origin_x=origin_x,
            origin_y=origin_y,
            origin_z=origin_z,
            width=width,
            length=length,
            height=height,
        )
        return _dump(result)

    @tool(description="Recommend the next survival or building goal based on current status.")
    async def recommend_next_goal(goal: str = "beat-minecraft") -> str:
        status = await bridge.get_status()
        recommendation = recommend_goal(status, goal)
        return _dump(recommendation.model_dump())

    @tool(description="Get the block name at position (x, y, z). Use to check what block is at a location before digging or placing.")
    async def get_block_at(x: int, y: int, z: int) -> str:
        return _dump(await bridge.get_block_at(x=x, y=y, z=z))

    @tool(description="Use/activate a block (door, button, lever, crafting table, chest, etc.) at (x, y, z). Bot pathfinds there then right-clicks. Pathfinding can break or place blocks in the way.")
    async def use_block(x: int, y: int, z: int) -> str:
        return _dump(await bridge.use_block(x=x, y=y, z=z))

    @tool(description="Equip an item from inventory. destination: hand, head, torso, legs, feet.")
    async def equip_item(item: str, destination: str = "hand") -> str:
        return _dump(await bridge.equip_item(item=item, destination=destination))

    @tool(description="Drop items from inventory onto the ground.")
    async def drop_item(item: str, count: int = 1) -> str:
        return _dump(await bridge.drop_item(item=item, count=count))

    @tool(description="Eat/consume a food item from inventory (restores hunger).")
    async def eat(item: str) -> str:
        return _dump(await bridge.eat(item=item))

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

    @tool(description="Sleep in a bed at (x, y, z). Bot pathfinds to the bed. Pass midnight in-game.")
    async def sleep(x: int, y: int, z: int) -> str:
        return _dump(await bridge.sleep(x=x, y=y, z=z))

    @tool(description="Wake up if the bot is sleeping.")
    async def wake() -> str:
        return _dump(await bridge.wake())

    @tool(description="Collect nearby dropped items on the ground within radius. Bot pathfinds to each; pathfinding can break blocks in the way.")
    async def collect_items(radius: int = 8) -> str:
        return _dump(await bridge.collect_items(radius=radius))

    @tool(description="Start fishing (must have fishing_rod in inventory).")
    async def fish() -> str:
        return _dump(await bridge.fish())

    @tool(description="Mount an entity (horse, donkey, boat, etc.) by name. Bot pathfinds to it.")
    async def mount_entity(name: str) -> str:
        return _dump(await bridge.mount_entity(name=name))

    @tool(description="Dismount from current vehicle or mount.")
    async def dismount() -> str:
        return _dump(await bridge.dismount())

    @tool(description="Interact with an entity (e.g. villager trade, animal feed). Bot pathfinds to the entity.")
    async def interact_entity(name: str) -> str:
        return _dump(await bridge.interact_entity(name=name))

    @tool(description="Stop current pathfinding and movement. Use when the bot is stuck or you want to cancel go_to_known_location.")
    async def stop_movement() -> str:
        return _dump(await bridge.stop_movement())

    server.collect(
        join_game,
        leave_game,
        get_bot_status,
        inspect_world,
        go_to_known_location,
        mine_resource,
        craft_items,
        place_block,
        dig_block,
        attack_entity,
        send_chat,
        read_chat,
        build_structure,
        recommend_next_goal,
        get_block_at,
        use_block,
        equip_item,
        drop_item,
        eat,
        look_at,
        jump,
        set_sprint,
        set_sneak,
        sleep,
        wake,
        collect_items,
        fish,
        mount_entity,
        dismount,
        interact_entity,
        stop_movement,
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

