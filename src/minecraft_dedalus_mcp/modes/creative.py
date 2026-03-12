from __future__ import annotations

from typing import Any

from ..bridge_client import BridgeClient


class CreativeActions:
    def __init__(self, bridge: BridgeClient) -> None:
        self._bridge = bridge

    async def run_command(self, command: str) -> dict[str, Any]:
        return await self._bridge.run_command(command=command)

    async def teleport(self, x: int, y: int, z: int) -> dict[str, Any]:
        return await self._bridge.run_command(command=f"/tp @s {x} {y} {z}")

    async def give_item(self, item: str, count: int = 1) -> dict[str, Any]:
        return await self._bridge.run_command(command=f"/give @s {item} {count}")

    async def set_gamemode(self, mode: str) -> dict[str, Any]:
        return await self._bridge.run_command(command=f"/gamemode {mode}")

    async def fill_blocks(
        self,
        x1: int, y1: int, z1: int,
        x2: int, y2: int, z2: int,
        block: str,
    ) -> dict[str, Any]:
        return await self._bridge.run_command(
            command=f"/fill {x1} {y1} {z1} {x2} {y2} {z2} {block}"
        )

    async def set_time(self, time_value: str) -> dict[str, Any]:
        return await self._bridge.run_command(command=f"/time set {time_value}")

    async def set_weather(self, weather: str) -> dict[str, Any]:
        return await self._bridge.run_command(command=f"/weather {weather}")

    async def summon_entity(self, entity: str, x: int, y: int, z: int) -> dict[str, Any]:
        return await self._bridge.run_command(command=f"/summon {entity} {x} {y} {z}")

    async def clear_inventory(self) -> dict[str, Any]:
        return await self._bridge.run_command(command="/clear @s")

    async def enchant(self, enchantment: str, level: int = 1) -> dict[str, Any]:
        return await self._bridge.run_command(command=f"/enchant @s {enchantment} {level}")

    async def kill_entities(self, target: str = "@e[type=!player]") -> dict[str, Any]:
        return await self._bridge.run_command(command=f"/kill {target}")
