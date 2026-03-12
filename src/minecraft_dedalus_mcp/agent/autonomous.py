"""Autonomous survival loop — proactively plays the game until stopped.

The loop repeats: inspect → recommend goal → run agent → remember results.
It can be started/stopped from chat or programmatically via the asyncio Event.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Callable, Coroutine

from dedalus_mcp.client import MCPClient

AUTONOMOUS_GOAL_PREFIX = (
    "You are playing Minecraft autonomously. No one told you what to do — decide for yourself based on the recommended goal below. "
    "Use create_plan if the goal has multiple steps, then execute each step. "
    "Use remember_location to save important places, remember_resource for ore veins you find. "
    "Use save_skill after completing a multi-tool sequence that could be reused. "
    "Use auto_eat if food is low. Use ensure_has_item before crafting to check materials. "
    "Use smelt_item when you have raw ores and a furnace. "
    "After finishing, summarize what you accomplished in 1-2 sentences via send_chat so the player can see.\n\n"
)

_STOP_PHRASES = frozenset({
    "stop", "pause", "halt", "wait", "come here",
    "stop autonomous", "stop playing", "quit playing",
    "stop surviving", "take a break", "freeze",
})

_START_PHRASES = frozenset({
    "start autonomous", "go autonomous", "play on your own",
    "start surviving", "survive", "keep playing",
    "play the game", "autoplay", "auto play",
    "do your thing", "go for it",
})


def is_start_command(message: str) -> bool:
    msg = message.strip().lower()
    return msg in _START_PHRASES or msg.startswith("start autonomous")


def is_stop_command(message: str) -> bool:
    msg = message.strip().lower()
    if msg in _STOP_PHRASES:
        return True
    for phrase in _STOP_PHRASES:
        if msg == phrase:
            return True
    return False


class AutonomousLoop:
    """Runs the agent in a proactive survival loop that can be started/stopped."""

    def __init__(
        self,
        mcp_url: str,
        run_agent_fn: Callable[..., Coroutine[Any, Any, None]],
        model: str = "",
        cycle_delay: float = 5.0,
        max_steps_per_cycle: int = 25,
        verbose: bool = True,
    ) -> None:
        self._mcp_url = mcp_url
        self._run_agent = run_agent_fn
        self._model = model or os.environ.get("DEDALUS_MODEL", "openai/gpt-5-nano-mini")
        self._cycle_delay = cycle_delay
        self._max_steps = max_steps_per_cycle
        self._verbose = verbose

        self._running = asyncio.Event()
        self._stop_requested = asyncio.Event()
        self._cancel_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._cycles_completed = 0
        self._last_goal = ""

    @property
    def is_active(self) -> bool:
        return self._running.is_set()

    @property
    def cycles_completed(self) -> int:
        return self._cycles_completed

    @property
    def last_goal(self) -> str:
        return self._last_goal

    def start(self) -> None:
        if self._running.is_set():
            return
        self._stop_requested.clear()
        self._cancel_event.clear()
        self._running.set()
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        self._stop_requested.set()
        self._cancel_event.set()
        self._running.clear()

    async def wait_until_stopped(self) -> None:
        if self._task:
            await self._task

    async def _get_goal(self) -> str | None:
        try:
            async with await MCPClient.connect(self._mcp_url) as client:
                result = await client.call_tool("recommend_next_goal", {"goal": "beat-minecraft"})
                for c in result.content:
                    if getattr(c, "type", None) == "text":
                        data = json.loads(c.text)
                        phase = data.get("phase", "unknown")
                        reason = data.get("reason", "")
                        checklist = data.get("checklist", [])
                        tools = data.get("suggested_tools", [])

                        goal_parts = [f"Phase: {phase}. {reason}"]
                        if checklist:
                            goal_parts.append("Checklist: " + "; ".join(checklist))
                        if tools:
                            goal_parts.append("Suggested tools: " + ", ".join(tools))
                        return "\n".join(goal_parts)
        except Exception as exc:
            if self._verbose:
                print(f"[autonomous] Failed to get goal: {exc}")
        return None

    async def _announce(self, message: str) -> None:
        try:
            async with await MCPClient.connect(self._mcp_url) as client:
                await client.call_tool("send_chat", {"message": message[:100]})
        except Exception:
            pass

    async def _loop(self) -> None:
        if self._verbose:
            print("[autonomous] Starting autonomous survival loop")
        await self._announce("Autonomous mode ON — I'll keep playing until you say 'stop'")

        try:
            while not self._stop_requested.is_set():
                goal_text = await self._get_goal()
                if not goal_text:
                    if self._verbose:
                        print("[autonomous] No goal available, waiting...")
                    await asyncio.sleep(self._cycle_delay)
                    continue

                self._last_goal = goal_text
                full_goal = AUTONOMOUS_GOAL_PREFIX + goal_text

                if self._verbose:
                    print(f"[autonomous] Cycle {self._cycles_completed + 1}: {goal_text[:120]}")

                if self._stop_requested.is_set():
                    break

                try:
                    self._cancel_event.clear()
                    await self._run_agent(
                        server_url=self._mcp_url,
                        model=self._model,
                        goal=full_goal,
                        max_steps=self._max_steps,
                        verbose=self._verbose,
                        cancel_event=self._cancel_event,
                    )
                    self._cycles_completed += 1
                except Exception as exc:
                    from minecraft_dedalus_mcp.agent_demo import AgentCancelled
                    if isinstance(exc, AgentCancelled):
                        if self._verbose:
                            print("[autonomous] Cycle cancelled")
                        break
                    error_msg = str(exc).lower()
                    if "rate limit" in error_msg or "429" in error_msg:
                        if self._verbose:
                            print("[autonomous] Rate limited, pausing 60s...")
                        await self._announce("Rate limited — pausing 60s")
                        await asyncio.sleep(60)
                    else:
                        if self._verbose:
                            print(f"[autonomous] Agent error: {exc}")
                        await asyncio.sleep(self._cycle_delay)

                if self._stop_requested.is_set():
                    break

                await asyncio.sleep(self._cycle_delay)

        finally:
            self._running.clear()
            if self._verbose:
                print(f"[autonomous] Stopped after {self._cycles_completed} cycles")
            await self._announce(f"Autonomous mode OFF ({self._cycles_completed} cycles done)")
