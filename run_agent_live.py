#!/usr/bin/env -S uv run python
"""Run the Dedalus agent so it acts autonomously in the world (bot must already be in-game)."""
from __future__ import annotations

import argparse
import asyncio
import os

from dotenv import load_dotenv

from minecraft_dedalus_mcp.agent_demo import run_agent

load_dotenv()

DEFAULT_GOAL = (
    "The bot is already in the Minecraft world. Inspect the world with inspect_world, "
    "then use recommend_next_goal to plan. Gather wood (mine oak_log), craft planks and tools, "
    "and build a small structure (e.g. pillar or hut). Work in short loops: inspect, decide, act."
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run the autonomous Dedalus agent. Start bridge + MCP server and join with run_join_game.py first."
    )
    p.add_argument(
        "--server-url",
        default=os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp"),
        help="MCP server URL (default: MCP_SERVER_URL or http://127.0.0.1:8000/mcp)",
    )
    p.add_argument("--model", default=os.environ.get("DEDALUS_MODEL", "openai/gpt-5-nano-mini"))
    p.add_argument("--max-steps", type=int, default=20)
    p.add_argument("--goal", default=DEFAULT_GOAL, help="Agent goal (bot is assumed already in-world)")
    return p.parse_args()


def main() -> None:
    if not os.getenv("DEDALUS_API_KEY"):
        raise SystemExit("DEDALUS_API_KEY is required. Set it in .env or export it.")
    args = _parse_args()
    asyncio.run(
        run_agent(
            server_url=args.server_url,
            model=args.model,
            goal=args.goal,
            max_steps=args.max_steps,
        )
    )


if __name__ == "__main__":
    main()
