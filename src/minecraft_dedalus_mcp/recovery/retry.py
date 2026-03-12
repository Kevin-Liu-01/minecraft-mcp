from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Any, Callable, Coroutine

from ..constants import MAX_RETRY_ATTEMPTS, RETRY_MOVE_OFFSET


class RecoveryStrategy(str, Enum):
    RETRY = "retry"
    MOVE_AND_RETRY = "move_and_retry"
    ALTERNATIVE_ARGS = "alternative_args"
    SKIP = "skip"


_MOVE_ERROR_PATTERNS = frozenset({
    "timed out",
    "path",
    "cannot read",
    "goal",
    "stuck",
})

_RESOURCE_ERROR_PATTERNS = frozenset({
    "no ",
    "not found",
    "unknown",
    "not in inventory",
})


def classify_error(error: str, tool_name: str) -> RecoveryStrategy:
    error_lower = error.lower()

    if any(pat in error_lower for pat in _MOVE_ERROR_PATTERNS):
        return RecoveryStrategy.MOVE_AND_RETRY

    if any(pat in error_lower for pat in _RESOURCE_ERROR_PATTERNS):
        if tool_name in ("mine_resource", "attack_entity", "craft_items"):
            return RecoveryStrategy.ALTERNATIVE_ARGS
        return RecoveryStrategy.SKIP

    return RecoveryStrategy.RETRY


def suggest_alternative_args(
    tool_name: str,
    original_args: dict[str, Any],
    error: str,
) -> dict[str, Any] | None:
    if tool_name == "mine_resource":
        name = original_args.get("name", "")
        alternatives = {
            "oak_log": ["birch_log", "spruce_log"],
            "birch_log": ["oak_log", "spruce_log"],
            "spruce_log": ["oak_log", "birch_log"],
            "cobblestone": ["stone", "deepslate"],
            "iron_ore": ["deepslate_iron_ore"],
        }
        alts = alternatives.get(name, [])
        if alts:
            new_args = dict(original_args)
            new_args["name"] = alts[0]
            return new_args

    if tool_name == "attack_entity":
        name = original_args.get("name", "")
        alternatives = {
            "cow": ["pig", "sheep", "chicken"],
            "pig": ["cow", "sheep", "chicken"],
            "zombie": ["skeleton", "spider"],
        }
        alts = alternatives.get(name, [])
        if alts:
            new_args = dict(original_args)
            new_args["name"] = alts[0]
            return new_args

    return None


def adjust_position_args(
    original_args: dict[str, Any],
    attempt: int,
) -> dict[str, Any]:
    new_args = dict(original_args)
    offset = RETRY_MOVE_OFFSET * attempt
    directions = [(1, 0), (0, 1), (-1, 0), (0, -1)]
    dx, dz = directions[attempt % len(directions)]
    if "x" in new_args:
        new_args["x"] = int(new_args["x"]) + dx * offset
    if "z" in new_args:
        new_args["z"] = int(new_args["z"]) + dz * offset
    return new_args


class ErrorRecovery:
    def __init__(self, max_retries: int = MAX_RETRY_ATTEMPTS) -> None:
        self._max_retries = max_retries

    async def execute_with_retry(
        self,
        fn: Callable[..., Coroutine[Any, Any, Any]],
        tool_name: str,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        last_error = ""
        for attempt in range(self._max_retries):
            try:
                start = time.time()
                result = await fn(**args)
                elapsed = (time.time() - start) * 1000
                return {
                    "result": result,
                    "attempts": attempt + 1,
                    "recovered": attempt > 0,
                    "duration_ms": round(elapsed),
                }
            except Exception as exc:
                last_error = str(exc)
                strategy = classify_error(last_error, tool_name)

                if strategy == RecoveryStrategy.SKIP:
                    break

                if strategy == RecoveryStrategy.MOVE_AND_RETRY:
                    args = adjust_position_args(args, attempt + 1)
                elif strategy == RecoveryStrategy.ALTERNATIVE_ARGS:
                    alt = suggest_alternative_args(tool_name, args, last_error)
                    if alt:
                        args = alt
                    else:
                        break

                await asyncio.sleep(0.5 * (attempt + 1))

        return {
            "result": None,
            "error": last_error,
            "attempts": self._max_retries,
            "recovered": False,
        }
