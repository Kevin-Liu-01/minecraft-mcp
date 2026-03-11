#!/usr/bin/env -S uv run python
"""Run the agent driven by Minecraft chat: treats in-game chat messages as natural language commands."""
from __future__ import annotations

import argparse
import asyncio
import json
import os

from dotenv import load_dotenv

from dedalus_mcp.client import MCPClient
from minecraft_dedalus_mcp.agent_demo import run_agent

load_dotenv()

CHAT_GOAL_PREFIX = (
    "The following was said in Minecraft chat. Treat it as a natural language command and perform the action. "
    "Use read_chat, get_bot_status, or inspect_world as needed, then use the appropriate tools (move, mine, place, attack, etc.). "
    "Do exactly what the player asked. "
    "Use send_chat only for short progress: one phrase per call (e.g. 'Moving to (x,y,z)', 'Mining oak_log', 'Done [mined 4]'). Never send 'On it!' or quote/echo any prior chat line.\n\n"
)

# Messages that look like our own acks or agent progress — never treat as player commands
_BOT_MESSAGE_PREFIXES = ("On it!", "Done!", "I'm doing", "All done", "Moving to", "Mining ", "Placing ", "Pausing ", "Arrived")
def _is_bot_like_message(message: str) -> bool:
    if not message or "[On it!" in message or "[Done!" in message:
        return True
    return message.strip().startswith(_BOT_MESSAGE_PREFIXES)


def _first_text(result) -> str | None:
    for c in result.content:
        if c.type == "text":
            return c.text
    return None


def _is_rate_limit_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return (
        "rate limit" in msg
        or "429" in msg
        or "too many requests" in msg
        or "quota" in msg
        or "limit exceeded" in msg
    )


def _prompt_continue(question: str, default_yes: bool = False) -> bool:
    """Blocking prompt; run from executor in async context."""
    suffix = " [Y/n]" if default_yes else " [y/N]"
    try:
        answer = input(question + suffix + " ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not answer:
        return default_yes
    return answer in ("y", "yes")


async def poll_chat_and_run(
    mcp_url: str,
    server_url: str,
    bot_username: str,
    seen: set[tuple[str, str]],
    max_seen: int,
    limit: int,
    commands_run: list[int],
    continue_after: int,
    rate_limit_wait_sec: float,
) -> None:
    async with await MCPClient.connect(mcp_url) as client:
        result = await client.call_tool("read_chat", {"limit": limit})
        text = _first_text(result)
        if not text:
            return
        data = json.loads(text)
        messages = data.get("messages") or []
    new_commands = []
    for m in messages:
        sender = m.get("sender") or m.get("username") or ""
        message = (m.get("message") or m.get("text") or "").strip()
        ts = m.get("timestamp") or ""
        if not message or sender == bot_username or sender == "server":
            continue
        if _is_bot_like_message(message):
            continue
        # Dedupe by (sender, message) only so same command isn't run twice (e.g. duplicate timestamps)
        key = (sender, message)
        if key not in seen:
            seen.add(key)
            new_commands.append(f"[{sender}]: {message}")
    while len(seen) > max_seen:
        seen.pop()
    if not new_commands:
        return
    goal = CHAT_GOAL_PREFIX + "\n".join(new_commands)
    print(f"[chat-agent] New command(s): {new_commands!r}")

    def _summary(cmds: list[str], max_len: int = 40) -> str:
        parts = []
        for c in cmds:
            if "]: " in c:
                raw = c.split("]: ", 1)[1].strip()
            else:
                raw = c.strip()
            if "[On it!" in raw or "[Done!" in raw:
                raw = "(command)"
            parts.append(raw)
        s = ", ".join(parts)
        s = (s[: max_len - 3] + "...") if len(s) > max_len else s
        return s[:max_len]

    ack_msg = f"On it! [{_summary(new_commands)}]"
    try:
        async with await MCPClient.connect(mcp_url) as client:
            await client.call_tool("send_chat", {"message": ack_msg})
    except Exception as e:
        print(f"[chat-agent] Could not send ack to chat: {e}")
    try:
        # Use local MCP URL so run_agent uses local tool execution (tools visible + run here)
        await run_agent(
            server_url=mcp_url,
            model=os.environ.get("DEDALUS_MODEL", "openai/gpt-5.2"),
            goal=goal,
            max_steps=25,
            verbose=True,
        )
        commands_run[0] += 1
        done_msg = f"Done! [{_summary(new_commands)}]"
        try:
            async with await MCPClient.connect(mcp_url) as client:
                await client.call_tool("send_chat", {"message": done_msg})
        except Exception as e:
            print(f"[chat-agent] Could not send done to chat: {e}")
    except Exception as e:
        if _is_rate_limit_error(e):
            print(f"[chat-agent] Rate limit or quota: {e}")
            try:
                async with await MCPClient.connect(mcp_url) as client:
                    await client.call_tool(
                        "send_chat",
                        {"message": f"Pausing (rate limit), back in {int(rate_limit_wait_sec)}s..."},
                    )
            except Exception:
                pass
            loop = asyncio.get_event_loop()
            wait_msg = f"Wait {int(rate_limit_wait_sec)}s and continue?"
            if await loop.run_in_executor(
                None, lambda: _prompt_continue(wait_msg, default_yes=True)
            ):
                print(f"[chat-agent] Waiting {rate_limit_wait_sec}s...")
                await asyncio.sleep(rate_limit_wait_sec)
                return
            raise SystemExit(0) from e
        raise


async def main_async(
    mcp_url: str,
    server_url: str,
    poll_interval: float,
    chat_limit: int,
    continue_after: int,
    rate_limit_wait_sec: float,
) -> None:
    if not os.getenv("DEDALUS_API_KEY"):
        raise SystemExit("DEDALUS_API_KEY is required. Set it in .env or export it.")
    seen: set[tuple[str, str]] = set()
    max_seen = 100
    commands_run: list[int] = [0]
    bot_username = ""
    async with await MCPClient.connect(mcp_url) as client:
        result = await client.call_tool("get_bot_status", {})
        text = _first_text(result)
        if text:
            data = json.loads(text)
            bot_username = (data.get("username") or "").strip()
    if not bot_username:
        print("[chat-agent] Could not get bot username; will process all chat (including bot's own).")
    else:
        print(f"[chat-agent] Ignoring messages from bot '{bot_username}'.")
    print(f"[chat-agent] Polling chat every {poll_interval}s. Say something in-game to command the bot.")
    if continue_after > 0:
        print(f"[chat-agent] After {continue_after} commands you'll be prompted to continue (avoids rate limits).")
    print("[chat-agent] Press Ctrl+C to stop.")
    loop = asyncio.get_event_loop()
    while True:
        if continue_after > 0 and commands_run[0] >= continue_after:
            ok = await loop.run_in_executor(
                None,
                lambda: _prompt_continue(
                    f"[chat-agent] {commands_run[0]} agent runs completed. Continue?",
                    default_yes=True,
                ),
            )
            if not ok:
                print("[chat-agent] Stopping.")
                return
            commands_run[0] = 0
        try:
            await poll_chat_and_run(
                mcp_url=mcp_url,
                server_url=server_url,
                bot_username=bot_username,
                seen=seen,
                max_seen=max_seen,
                limit=chat_limit,
                commands_run=commands_run,
                continue_after=continue_after,
                rate_limit_wait_sec=rate_limit_wait_sec,
            )
        except SystemExit:
            raise
        except Exception as e:
            print(f"[chat-agent] Error: {e}")
        await asyncio.sleep(poll_interval)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run the agent from Minecraft chat: in-game messages are treated as natural language commands."
    )
    p.add_argument(
        "--mcp-url",
        default=os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp"),
        help="MCP server URL for polling chat (local)",
    )
    p.add_argument(
        "--server-url",
        default=os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp"),
        help="MCP server URL passed to the Dedalus agent (must be reachable from the internet if using Dedalus cloud; use ngrok)",
    )
    p.add_argument("--poll-interval", type=float, default=8.0, help="Seconds between chat polls")
    p.add_argument("--chat-limit", type=int, default=20, help="Number of chat messages to fetch per poll")
    p.add_argument(
        "--continue-after",
        type=int,
        default=100,
        help="After this many agent runs, prompt to continue (0 = never prompt). Helps avoid rate limits.",
    )
    p.add_argument(
        "--rate-limit-wait",
        type=float,
        default=60.0,
        help="When rate limit is detected, wait this many seconds before offering to continue (default 60).",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    asyncio.run(
        main_async(
            mcp_url=args.mcp_url,
            server_url=args.server_url,
            poll_interval=args.poll_interval,
            chat_limit=args.chat_limit,
            continue_after=args.continue_after,
            rate_limit_wait_sec=args.rate_limit_wait,
        )
    )


if __name__ == "__main__":
    main()
