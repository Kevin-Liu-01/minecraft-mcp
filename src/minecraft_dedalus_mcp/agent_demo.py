from __future__ import annotations

import argparse
import asyncio
import os

from dotenv import load_dotenv

from dedalus_labs import AsyncDedalus, DedalusRunner


load_dotenv()

DEFAULT_AGENT_INSTRUCTIONS = (
    "You are controlling a Minecraft bot. Always inspect the world first, "
    "then work in short safe loops. If the goal is survival-oriented, call "
    "recommend_next_goal before starting multi-step execution."
)


async def run_agent(
    server_url: str,
    model: str,
    goal: str,
    *,
    max_steps: int = 12,
    verbose: bool = True,
) -> None:
    api_key = os.getenv("DEDALUS_API_KEY")
    if not api_key:
        raise SystemExit("DEDALUS_API_KEY is required to run the Dedalus agent demo.")

    client = AsyncDedalus(api_key=api_key)
    runner = DedalusRunner(client, verbose=verbose)
    result = await runner.run(
        input=goal,
        model=model,
        mcp_servers=[server_url],
        instructions=DEFAULT_AGENT_INSTRUCTIONS,
        max_steps=max_steps,
        stream=False,
    )
    print(result.final_output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Dedalus agent against the Minecraft MCP server")
    parser.add_argument("--server-url", default="http://127.0.0.1:8000/mcp")
    parser.add_argument("--model", default="openai/gpt-5.2")
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument(
        "--goal",
        default="Join the world, inspect it, gather some wood, and build a starter pillar.",
    )
    args = parser.parse_args()
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
