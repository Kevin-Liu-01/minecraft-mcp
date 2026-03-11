from __future__ import annotations

from typing import Any

import httpx

from .models import BotStatus, WorldSnapshot


class BridgeError(RuntimeError):
    """Raised when the Node bridge returns an application-level error."""


class BridgeClient:
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
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

    async def send_chat(self, *, message: str) -> dict[str, Any]:
        return await self._request("POST", "/actions/send_chat", json={"message": message})

    async def read_chat(self, *, limit: int) -> dict[str, Any]:
        return await self._request("GET", "/chat/messages", params={"limit": limit})

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

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = await self._client.request(method, path, json=json, params=params)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise BridgeError(payload.get("error", "Unknown bridge error"))
        return payload["result"]

