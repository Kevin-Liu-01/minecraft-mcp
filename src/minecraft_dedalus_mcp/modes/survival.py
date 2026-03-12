from __future__ import annotations

from typing import Any

from ..bridge_client import BridgeClient
from ..constants import SMELTABLE_ITEMS


class SurvivalActions:
    def __init__(self, bridge: BridgeClient) -> None:
        self._bridge = bridge

    async def ensure_has_item(
        self,
        item: str,
        count: int = 1,
    ) -> dict[str, Any]:
        status = await self._bridge.get_status()
        current = 0
        for entry in status.inventory:
            if entry.item == item:
                current += entry.count
        if current >= count:
            return {"action": "ensure_has_item", "item": item, "had": current, "needed": count, "acquired": False}

        needed = count - current
        if item in SMELTABLE_ITEMS.values():
            raw_item = next((k for k, v in SMELTABLE_ITEMS.items() if v == item), None)
            if raw_item:
                return {
                    "action": "ensure_has_item",
                    "item": item,
                    "suggestion": f"Mine {raw_item} and smelt into {item}",
                    "needed": needed,
                }

        return {
            "action": "ensure_has_item",
            "item": item,
            "needed": needed,
            "suggestion": f"Craft or gather {needed} more {item}",
        }

    async def safe_move_to(
        self,
        x: int,
        y: int,
        z: int,
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        last_error = None
        for attempt in range(max_attempts):
            try:
                result = await self._bridge.move_to(
                    x=x, y=y, z=z, range=2, timeout_ms=30000
                )
                return {**result, "attempts": attempt + 1}
            except Exception as exc:
                last_error = str(exc)
                x += 2
                z += 2
        return {
            "action": "safe_move_to",
            "reached": False,
            "attempts": max_attempts,
            "error": last_error,
        }

    async def auto_eat(self) -> dict[str, Any]:
        status = await self._bridge.get_status()
        if status.food is not None and status.food >= 18:
            return {"action": "auto_eat", "skipped": True, "food": status.food}

        food_priority = [
            "cooked_beef", "cooked_porkchop", "cooked_chicken",
            "bread", "baked_potato", "cooked_mutton", "apple",
        ]
        for food in food_priority:
            for entry in status.inventory:
                if entry.item == food and entry.count > 0:
                    result = await self._bridge.eat(item=food)
                    return {**result, "food_item": food}

        return {"action": "auto_eat", "skipped": True, "reason": "no food available"}
