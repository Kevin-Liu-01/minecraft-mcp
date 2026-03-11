from __future__ import annotations

import argparse
import asyncio
import json

from dedalus_mcp import MCPServer, tool

from .bridge_client import BridgeClient
from .playbook import recommend_goal


def _dump(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def build_server(bridge: BridgeClient) -> MCPServer:
    server = MCPServer(
        "minecraft-lan-mcp",
        instructions=(
            "You control a Minecraft bot over LAN via a Mineflayer bridge. "
            "Prefer inspect_world before long action chains, and use recommend_next_goal "
            "to plan survival progression."
        ),
    )

    @tool(description="Connect the bot to a Minecraft LAN world or local server.")
    async def join_game(
        host: str = "127.0.0.1",
        port: int = 25565,
        username: str = "DedalusBot",
        auth: str = "offline",
        version: str | None = None,
    ) -> str:
        result = await bridge.join_game(host=host, port=port, username=username, auth=auth, version=version)
        return _dump(result.model_dump())

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

    @tool(description="Move the bot near a target coordinate in the world.")
    async def go_to_known_location(
        x: int,
        y: int,
        z: int,
        range: int = 1,
        timeout_ms: int = 30000,
    ) -> str:
        result = await bridge.move_to(x=x, y=y, z=z, range=range, timeout_ms=timeout_ms)
        return _dump(result)

    @tool(description="Mine a named resource block or simulated resource drop.")
    async def mine_resource(name: str, count: int = 1, max_distance: int = 32) -> str:
        result = await bridge.mine_resource(name=name, count=count, max_distance=max_distance)
        return _dump(result)

    @tool(description="Craft a named item using currently available inventory.")
    async def craft_items(item: str, count: int = 1) -> str:
        result = await bridge.craft_items(item=item, count=count)
        return _dump(result)

    @tool(description="Place a block at an exact target coordinate.")
    async def place_block(block: str, x: int, y: int, z: int) -> str:
        result = await bridge.place_block(block=block, x=x, y=y, z=z)
        return _dump(result)

    @tool(description="Dig a block at an exact target coordinate.")
    async def dig_block(x: int, y: int, z: int) -> str:
        result = await bridge.dig_block(x=x, y=y, z=z)
        return _dump(result)

    @tool(description="Attack a nearby entity by name.")
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

