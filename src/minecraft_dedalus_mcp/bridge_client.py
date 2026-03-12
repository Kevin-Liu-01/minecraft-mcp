from __future__ import annotations

from typing import Any

import httpx

from .models import BotStatus, WorldSnapshot


class BridgeError(RuntimeError):
    """Raised when the Node bridge returns an application-level error."""


class BridgeClient:
    def __init__(self, base_url: str, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def join_game(
        self,
        *,
        host: str,
        port: int,
        username: str,
        auth: str,
        version: str | None,
    ) -> BotStatus:
        payload = {
            "host": host,
            "port": port,
            "username": username,
            "auth": auth,
            "version": version,
        }
        result = await self._request("POST", "/session/connect", json=payload)
        return BotStatus.model_validate(result)

    async def leave_game(self) -> dict[str, Any]:
        return await self._request("POST", "/session/disconnect")

    async def get_status(self) -> BotStatus:
        result = await self._request("GET", "/session/status")
        return BotStatus.model_validate(result)

    async def inspect_world(self, radius: int = 16) -> WorldSnapshot:
        result = await self._request("GET", "/world/snapshot", params={"radius": radius})
        return WorldSnapshot.model_validate(result)

    async def move_to(self, *, x: int, y: int, z: int, range: int, timeout_ms: int) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/actions/move_to",
            json={"x": x, "y": y, "z": z, "range": range, "timeout_ms": timeout_ms},
        )

    async def mine_resource(self, *, name: str, count: int, max_distance: int) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/actions/mine_resource",
            json={"name": name, "count": count, "max_distance": max_distance},
        )

    async def craft_items(self, *, item: str, count: int) -> dict[str, Any]:
        return await self._request("POST", "/actions/craft_items", json={"item": item, "count": count})

    async def place_block(self, *, block: str, x: int, y: int, z: int) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/actions/place_block",
            json={"block": block, "x": x, "y": y, "z": z},
        )

    async def dig_block(self, *, x: int, y: int, z: int) -> dict[str, Any]:
        return await self._request("POST", "/actions/dig_block", json={"x": x, "y": y, "z": z})

    async def attack_entity(self, *, name: str, count: int) -> dict[str, Any]:
        return await self._request("POST", "/actions/attack_entity", json={"name": name, "count": count})

    async def go_to_player(self, *, name: str) -> dict[str, Any]:
        return await self._request("POST", "/actions/go_to_player", json={"name": name})

    async def go_to_entity(self, *, name: str = "") -> dict[str, Any]:
        return await self._request("POST", "/actions/go_to_entity", json={"name": name})

    async def send_chat(self, *, message: str) -> dict[str, Any]:
        return await self._request("POST", "/actions/send_chat", json={"message": message})

    async def read_chat(self, *, limit: int) -> dict[str, Any]:
        return await self._request("GET", "/chat/messages", params={"limit": limit})

    async def find_players(self) -> dict[str, Any]:
        return await self._request("GET", "/players")

    async def find_entities(self, *, radius: int = 32) -> dict[str, Any]:
        return await self._request("GET", "/entities", params={"radius": radius})

    async def build_structure(
        self,
        *,
        preset: str,
        material: str,
        origin_x: int,
        origin_y: int,
        origin_z: int,
        width: int,
        length: int,
        height: int,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/actions/build_structure",
            json={
                "preset": preset,
                "material": material,
                "origin_x": origin_x,
                "origin_y": origin_y,
                "origin_z": origin_z,
                "width": width,
                "length": length,
                "height": height,
            },
        )

    async def build_quick(
        self,
        *,
        shape: str,
        material: str = "",
        height: int | None = None,
        width: int | None = None,
        length: int | None = None,
        radius: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"shape": shape}
        if material: payload["material"] = material
        if height is not None: payload["height"] = height
        if width is not None: payload["width"] = width
        if length is not None: payload["length"] = length
        if radius is not None: payload["radius"] = radius
        return await self._request("POST", "/actions/build_quick", json=payload)

    async def get_block_at(self, *, x: int, y: int, z: int) -> dict[str, Any]:
        return await self._request("POST", "/actions/get_block_at", json={"x": x, "y": y, "z": z})

    async def use_block(self, *, x: int, y: int, z: int) -> dict[str, Any]:
        return await self._request("POST", "/actions/use_block", json={"x": x, "y": y, "z": z})

    async def equip_item(self, *, item: str, destination: str = "hand") -> dict[str, Any]:
        return await self._request(
            "POST", "/actions/equip_item", json={"item": item, "destination": destination}
        )

    async def drop_item(self, *, item: str, count: int = 1) -> dict[str, Any]:
        return await self._request("POST", "/actions/drop_item", json={"item": item, "count": count})

    async def eat(self, *, item: str) -> dict[str, Any]:
        return await self._request("POST", "/actions/eat", json={"item": item})

    async def look_at(self, *, x: int, y: int, z: int) -> dict[str, Any]:
        return await self._request("POST", "/actions/look_at", json={"x": x, "y": y, "z": z})

    async def jump(self) -> dict[str, Any]:
        return await self._request("POST", "/actions/jump", json={})

    async def set_sprint(self, *, sprint: bool = True) -> dict[str, Any]:
        return await self._request("POST", "/actions/set_sprint", json={"sprint": sprint})

    async def set_sneak(self, *, sneak: bool = True) -> dict[str, Any]:
        return await self._request("POST", "/actions/set_sneak", json={"sneak": sneak})

    async def sleep(self, *, x: int, y: int, z: int) -> dict[str, Any]:
        return await self._request("POST", "/actions/sleep", json={"x": x, "y": y, "z": z})

    async def wake(self) -> dict[str, Any]:
        return await self._request("POST", "/actions/wake", json={})

    async def collect_items(self, *, radius: int = 8) -> dict[str, Any]:
        return await self._request("POST", "/actions/collect_items", json={"radius": radius})

    async def fish(self) -> dict[str, Any]:
        return await self._request("POST", "/actions/fish", json={})

    async def mount_entity(self, *, name: str) -> dict[str, Any]:
        return await self._request("POST", "/actions/mount_entity", json={"name": name})

    async def dismount(self) -> dict[str, Any]:
        return await self._request("POST", "/actions/dismount", json={})

    async def interact_entity(self, *, name: str) -> dict[str, Any]:
        return await self._request("POST", "/actions/interact_entity", json={"name": name})

    async def stop_movement(self) -> dict[str, Any]:
        return await self._request("POST", "/actions/stop_movement", json={})

    async def smelt_item(self, *, item: str, count: int = 1, fuel: str = "coal") -> dict[str, Any]:
        return await self._request(
            "POST", "/actions/smelt_item", json={"item": item, "count": count, "fuel": fuel}
        )

    async def run_command(self, *, command: str) -> dict[str, Any]:
        return await self._request("POST", "/actions/run_command", json={"command": command})

    async def build_blueprint(self, *, blocks: list[dict[str, Any]]) -> dict[str, Any]:
        return await self._request("POST", "/actions/build_blueprint", json={"blocks": blocks})

    async def hunt(self, *, name: str = "", count: int = 5, radius: int = 48) -> dict[str, Any]:
        return await self._request("POST", "/actions/hunt", json={"name": name, "count": count, "radius": radius})

    async def gather_wood(self, *, count: int = 16, type: str = "") -> dict[str, Any]:
        return await self._request("POST", "/actions/gather_wood", json={"count": count, "type": type})

    async def clear_area(self, *, radius: int = 3, depth: int = 1) -> dict[str, Any]:
        return await self._request("POST", "/actions/clear_area", json={"radius": radius, "depth": depth})

    async def follow_player(self, *, name: str, duration_seconds: int = 30) -> dict[str, Any]:
        return await self._request("POST", "/actions/follow_player", json={"name": name, "duration_seconds": duration_seconds})

    async def defend_area(self, *, radius: int = 10, duration_seconds: int = 60) -> dict[str, Any]:
        return await self._request("POST", "/actions/defend_area", json={"radius": radius, "duration_seconds": duration_seconds})

    async def store_items(self, *, item: str = "", chest_x: int | None = None, chest_y: int | None = None, chest_z: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"item": item}
        if chest_x is not None: payload["chest_x"] = chest_x
        if chest_y is not None: payload["chest_y"] = chest_y
        if chest_z is not None: payload["chest_z"] = chest_z
        return await self._request("POST", "/actions/store_items", json=payload)

    async def retrieve_items(self, *, item: str, count: int = 64, chest_x: int | None = None, chest_y: int | None = None, chest_z: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"item": item, "count": count}
        if chest_x is not None: payload["chest_x"] = chest_x
        if chest_y is not None: payload["chest_y"] = chest_y
        if chest_z is not None: payload["chest_z"] = chest_z
        return await self._request("POST", "/actions/retrieve_items", json=payload)

    async def plant_crops(self, *, seed: str = "wheat_seeds", rows: int = 3, cols: int = 3) -> dict[str, Any]:
        return await self._request("POST", "/actions/plant_crops", json={"seed": seed, "rows": rows, "cols": cols})

    async def harvest_crops(self, *, radius: int = 6) -> dict[str, Any]:
        return await self._request("POST", "/actions/harvest_crops", json={"radius": radius})

    async def make_tools(self, *, material: str = "") -> dict[str, Any]:
        return await self._request("POST", "/actions/make_tools", json={"material": material})

    async def smelt_all(self, *, item: str, fuel: str = "coal") -> dict[str, Any]:
        return await self._request("POST", "/actions/smelt_all", json={"item": item, "fuel": fuel})

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = await self._client.request(method, path, json=json, params=params)
        try:
            payload = response.json()
        except Exception:
            payload = {}
        if not response.is_success:
            msg = payload.get("error") if isinstance(payload, dict) else None
            if not msg:
                msg = f"Bridge returned {response.status_code}: {response.text[:500] if response.text else 'no body'}"
            raise BridgeError(msg)
        if not payload.get("ok"):
            raise BridgeError(payload.get("error", "Unknown bridge error"))
        return payload["result"]

