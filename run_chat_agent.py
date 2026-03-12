#!/usr/bin/env -S uv run python
"""Run the agent driven by Minecraft chat: treats in-game chat messages as natural language commands.

Supports autonomous mode: say "start autonomous" in chat and the bot proactively
plays the game (inspect -> plan -> execute -> learn). Say "stop" to return to
reactive chat-command mode.

The agent runs in a background task so chat polling continues during execution.
Typing "stop" or a new *different* command mid-run cancels the current agent task.
The same command is never re-triggered while already running.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from collections import OrderedDict
from dataclasses import dataclass, field

from dotenv import load_dotenv

from dedalus_mcp.client import MCPClient
from minecraft_dedalus_mcp.agent_demo import (
    run_agent,
    AgentCancelled,
    AgentStatus,
    CORE_TOOL_NAMES,
)
from minecraft_dedalus_mcp.agent.autonomous import AutonomousLoop, is_start_command, is_stop_command
from minecraft_dedalus_mcp import event_log

load_dotenv()

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)

_CHAT_GOAL_TEMPLATE = (
    "Player '{sender}' said: {message}\n"
    "IMPORTANT: When they say 'me', 'my', or 'I', they mean player '{sender}'. "
    "Use name='{sender}' for go_to_player, follow_player, attack_entity, etc. "
    "Execute immediately. Your status is above — do NOT call get_bot_status.\n"
)

_BOT_MESSAGE_PREFIXES = (
    "On it!", "Done!", "Done:", "Working on:", "Finished:", "Stopped:", "Ran out of",
    "Got no response", "Error:", "I'm doing", "All done",
    "Moving to", "Mining ", "Placing ", "Pausing ", "Arrived", "Autonomous mode",
)

_GAME_NOTIFICATION_PATTERNS = (
    "Set own game mode to",
    "Gamerule ",
    "Killed ",
    " has made the advancement",
    " joined the game",
    " left the game",
    "Unable to open",
    "commands.give.success",
    "Teleported ",
    "Given ",
    " was killed",
    " was slain",
    " fell from",
    " drowned",
    " burned",
    " blew up",
    " hit the ground",
    " tried to swim",
    " suffocated",
    " starved",
    " withered away",
)


def _is_game_notification(message: str) -> bool:
    stripped = message.strip()
    if stripped.endswith("]") and any(stripped.startswith(p) or p in stripped for p in _GAME_NOTIFICATION_PATTERNS):
        return True
    return any(stripped.startswith(p) for p in _GAME_NOTIFICATION_PATTERNS)


def _is_bot_like_message(message: str) -> bool:
    if not message:
        return True
    stripped = message.strip()
    if any(tag in stripped for tag in ("[On it!", "[Done!", "[Done:", "[Working on:", "[Finished:", "[Stopped:", "[Ran out", "[Got no", "[Error:")):
        return True
    if _is_game_notification(stripped):
        return True
    return stripped.startswith(_BOT_MESSAGE_PREFIXES)


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
    suffix = " [Y/n]" if default_yes else " [y/N]"
    try:
        answer = input(question + suffix + " ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not answer:
        return default_yes
    return answer in ("y", "yes")


def _build_goal(structured: list[_ChatCommand]) -> str:
    parts: list[str] = []
    for cmd in structured:
        parts.append(
            _CHAT_GOAL_TEMPLATE.format(sender=cmd.sender, message=cmd.message)
        )
    return "\n".join(parts)


def _command_summary(cmds: list[str], max_len: int = 50) -> str:
    parts = []
    for c in cmds:
        raw = c.split("]: ", 1)[1].strip() if "]: " in c else c.strip()
        if any(tag in raw for tag in ("[On it!", "[Done!", "[Done:", "[Working on:", "[Finished:", "[Stopped:", "[Ran out", "[Got no", "[Error:")):
            continue
        parts.append(raw)
    s = ", ".join(parts) if parts else "(command)"
    return (s[: max_len - 3] + "...") if len(s) > max_len else s


async def _send_chat(mcp_client: MCPClient, message: str) -> None:
    try:
        await mcp_client.call_tool("send_chat", {"message": message})
    except Exception as e:
        print(f"[chat-agent] Could not send chat: {e}")


async def _force_stop_bridge(mcp_client: MCPClient) -> None:
    """Send stop_movement to the bridge to immediately halt bot actions."""
    import httpx
    # Hit the bridge directly for speed — bypass MCP server
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post("http://127.0.0.1:8787/actions/stop_movement", json={})
    except Exception:
        pass
    # Also try through MCP as fallback
    try:
        await mcp_client.call_tool("stop_movement", {})
    except Exception:
        pass


async def _fetch_chat(mcp_client: MCPClient, limit: int) -> list[dict]:
    try:
        result = await mcp_client.call_tool("read_chat", {"limit": limit})
        text = _first_text(result)
        if text:
            return json.loads(text).get("messages") or []
    except Exception as e:
        print(f"[chat-agent] Chat poll error: {e}")
    return []


@dataclass
class _ChatCommand:
    sender: str
    message: str
    formatted: str

@dataclass
class ParsedChat:
    """Result of parsing new chat messages."""
    commands: list[str] = field(default_factory=list)
    structured: list[_ChatCommand] = field(default_factory=list)
    stop_requested: bool = False
    start_autonomous: bool = False
    stop_autonomous: bool = False


def _parse_new_messages(
    messages: list[dict],
    bot_username: str,
    seen: OrderedDict[tuple[str, str], None],
    max_seen: int,
) -> ParsedChat:
    result = ParsedChat()
    for m in messages:
        sender = m.get("sender") or m.get("username") or ""
        message = (m.get("message") or m.get("text") or "").strip()
        if not message or sender == bot_username or sender == "server":
            continue
        if _is_bot_like_message(message):
            continue
        key = (sender, message)
        if key in seen:
            continue
        seen[key] = None

        if is_stop_command(message):
            result.stop_requested = True
            result.stop_autonomous = True
            print(f"[chat-agent] Player '{sender}' said stop")
            continue
        if is_start_command(message):
            result.start_autonomous = True
            print(f"[chat-agent] Player '{sender}' triggered autonomous mode")
            continue

        fmt = f"[{sender}]: {message}"
        result.commands.append(fmt)
        result.structured.append(_ChatCommand(sender=sender, message=message, formatted=fmt))

    while len(seen) > max_seen:
        seen.popitem(last=False)
    return result


@dataclass
class AgentTaskState:
    """Tracks the currently running agent background task."""
    task: asyncio.Task[None] | None = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    summary: str = ""

    @property
    def is_running(self) -> bool:
        return self.task is not None and not self.task.done()

    def cancel(self, mcp_client: MCPClient | None = None) -> None:
        if self.is_running:
            self.cancel_event.set()
            print(f"[chat-agent] Cancelling: {self.summary}")
            if mcp_client:
                asyncio.ensure_future(_force_stop_bridge(mcp_client))

    def reset(self) -> None:
        self.task = None
        self.cancel_event = asyncio.Event()
        self.summary = ""


async def _run_agent_task(
    server_url: str,
    goal: str,
    summary: str,
    mcp_client: MCPClient,
    cancel_event: asyncio.Event,
    commands_run: list[int],
) -> None:
    await _send_chat(mcp_client, f"Working on: {summary}")
    try:
        status = await run_agent(
            server_url=server_url,
            model=os.environ.get("DEDALUS_MODEL", "openai/gpt-4o-mini"),
            goal=goal,
            max_steps=25,
            verbose=True,
            cancel_event=cancel_event,
            tool_filter=CORE_TOOL_NAMES,
        )
        commands_run[0] += 1
        if status == AgentStatus.COMPLETED:
            await _send_chat(mcp_client, f"Done: {summary}")
        elif status == AgentStatus.MAX_STEPS:
            await _send_chat(mcp_client, f"Ran out of steps on: {summary}")
        elif status == AgentStatus.NO_RESPONSE:
            await _send_chat(mcp_client, f"Got no response for: {summary}")
    except AgentCancelled:
        print(f"[chat-agent] Agent stopped: {summary}")
        await _send_chat(mcp_client, f"Stopped: {summary}")
    except Exception as e:
        if _is_rate_limit_error(e):
            print(f"[chat-agent] Rate limit: {e}")
            await _send_chat(mcp_client, "Pausing (rate limit)")
            await asyncio.sleep(60)
        else:
            print(f"[chat-agent] Agent error: {e}")
            await _send_chat(mcp_client, f"Error: {str(e)[:40]}")


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

    seen: OrderedDict[tuple[str, str], None] = OrderedDict()
    max_seen = 200
    commands_run: list[int] = [0]

    async with await MCPClient.connect(mcp_url) as mcp_client:
        result = await mcp_client.call_tool("get_bot_status", {})
        text = _first_text(result)
        bot_username = ""
        if text:
            data = json.loads(text)
            bot_username = (data.get("username") or "").strip()
        if not bot_username:
            print("[chat-agent] Could not get bot username; will process all chat.")
        else:
            print(f"[chat-agent] Ignoring messages from bot '{bot_username}'.")

        initial_msgs = await _fetch_chat(mcp_client, chat_limit)
        for m in initial_msgs:
            sender = m.get("sender") or m.get("username") or ""
            message = (m.get("message") or m.get("text") or "").strip()
            if message and sender:
                seen[(sender, message)] = None
        if initial_msgs:
            print(f"[chat-agent] Pre-seeded {len(seen)} messages from chat history (won't re-trigger).")

        autonomous_loop = AutonomousLoop(
            mcp_url=mcp_url,
            run_agent_fn=run_agent,
            model=os.environ.get("DEDALUS_MODEL", "openai/gpt-4o-mini"),
            cycle_delay=5.0,
            max_steps_per_cycle=25,
            verbose=True,
        )

        agent_state = AgentTaskState()

        print(f"[chat-agent] Polling chat every {poll_interval}s. Say something in-game to command the bot.")
        print("[chat-agent] Say 'start autonomous' to play on its own, 'stop' to halt anything.")
        if continue_after > 0:
            print(f"[chat-agent] After {continue_after} commands you'll be prompted to continue.")
        print("[chat-agent] Press Ctrl+C to stop.")

        try:
            while True:
                if continue_after > 0 and commands_run[0] >= continue_after:
                    agent_state.cancel(mcp_client)
                    if autonomous_loop.is_active:
                        autonomous_loop.stop()
                    ev_loop = asyncio.get_event_loop()
                    ok = await ev_loop.run_in_executor(
                        None,
                        lambda: _prompt_continue(
                            f"[chat-agent] {commands_run[0]} runs completed. Continue?",
                            default_yes=True,
                        ),
                    )
                    if not ok:
                        print("[chat-agent] Stopping.")
                        return
                    commands_run[0] = 0

                chat_messages = await _fetch_chat(mcp_client, chat_limit)
                parsed = _parse_new_messages(chat_messages, bot_username, seen, max_seen)

                if parsed.stop_requested or parsed.stop_autonomous:
                    if agent_state.is_running:
                        agent_state.cancel(mcp_client)
                    if autonomous_loop.is_active:
                        autonomous_loop.stop()

                if parsed.start_autonomous and not parsed.stop_requested:
                    if agent_state.is_running:
                        agent_state.cancel(mcp_client)
                    if not autonomous_loop.is_active:
                        autonomous_loop.start()

                if parsed.commands:
                    new_summary = _command_summary(parsed.commands)

                    if agent_state.is_running and agent_state.summary == new_summary:
                        print(f"[chat-agent] Same task already running, skipping: {new_summary}")
                    else:
                        if autonomous_loop.is_active:
                            print("[chat-agent] Direct command received — pausing autonomous mode")
                            autonomous_loop.stop()

                        if agent_state.is_running:
                            agent_state.cancel(mcp_client)
                            await asyncio.sleep(0.1)

                        goal = _build_goal(parsed.structured)
                        print(f"[chat-agent] New command(s): {parsed.commands!r}")
                        event_log.emit("chat_command", commands=parsed.commands)

                        agent_state.reset()
                        agent_state.summary = new_summary
                        agent_state.task = asyncio.create_task(
                            _run_agent_task(
                                server_url=server_url,
                                goal=goal,
                                summary=new_summary,
                                mcp_client=mcp_client,
                                cancel_event=agent_state.cancel_event,
                                commands_run=commands_run,
                            )
                        )

                if not agent_state.is_running and agent_state.task is not None:
                    exc = agent_state.task.exception() if not agent_state.task.cancelled() else None
                    if exc and not isinstance(exc, (AgentCancelled, SystemExit)):
                        print(f"[chat-agent] Task error: {exc}")
                    agent_state.reset()

                await asyncio.sleep(poll_interval)

        finally:
            if agent_state.is_running:
                agent_state.cancel()
                try:
                    await asyncio.wait_for(agent_state.task, timeout=5.0)
                except (asyncio.TimeoutError, Exception):
                    pass
            if autonomous_loop.is_active:
                autonomous_loop.stop()
                await autonomous_loop.wait_until_stopped()


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
        help="MCP server URL passed to the Dedalus agent",
    )
    p.add_argument("--poll-interval", type=float, default=1.5, help="Seconds between chat polls")
    p.add_argument("--chat-limit", type=int, default=20, help="Number of chat messages to fetch per poll")
    p.add_argument(
        "--continue-after",
        type=int,
        default=100,
        help="After this many agent runs, prompt to continue (0 = never).",
    )
    p.add_argument(
        "--rate-limit-wait",
        type=float,
        default=60.0,
        help="Seconds to wait on rate limit (default 60).",
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
