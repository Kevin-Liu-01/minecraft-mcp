"""Demo: Autonomous Survival Mode — the bot plays on its own until you stop it.

This demo starts the autonomous loop directly (without chat polling).
In normal usage, say "start autonomous" in Minecraft chat instead.

Requires: bridge + MCP server running, bot joined to a game.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys

from dotenv import load_dotenv

from minecraft_dedalus_mcp.agent.autonomous import AutonomousLoop
from minecraft_dedalus_mcp.agent_demo import run_agent

load_dotenv()

MCP_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")


async def main() -> None:
    print("=== Autonomous Survival Demo ===\n")
    print("The bot will proactively play the game:")
    print("  inspect → recommend goal → plan → execute → remember → repeat\n")
    print("Press Ctrl+C to stop.\n")

    loop_runner = AutonomousLoop(
        mcp_url=MCP_URL,
        run_agent_fn=run_agent,
        model=os.environ.get("DEDALUS_MODEL", "openai/gpt-4o-mini"),
        cycle_delay=5.0,
        max_steps_per_cycle=25,
        verbose=True,
    )

    stop_event = asyncio.Event()

    def _on_signal() -> None:
        print("\n[demo] Ctrl+C received — stopping autonomous loop...")
        loop_runner.stop()
        stop_event.set()

    aio_loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        aio_loop.add_signal_handler(sig, _on_signal)

    loop_runner.start()
    await stop_event.wait()
    await loop_runner.wait_until_stopped()

    print(f"\n[demo] Completed {loop_runner.cycles_completed} autonomous cycles.")
    if loop_runner.last_goal:
        print(f"[demo] Last goal was: {loop_runner.last_goal[:120]}")
    print("\n=== Autonomous Demo Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
