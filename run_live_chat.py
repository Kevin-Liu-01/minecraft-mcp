#!/usr/bin/env -S uv run python
"""One-command launcher: start bridge, MCP server, join the game, then run the chat-driven agent.

Use in-game chat to command the bot (e.g. "mine 10 dirt", "go to the tree").
Requires Minecraft Java Edition with a world opened to LAN (or a server).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from dedalus_mcp.client import MCPClient
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
DEFAULT_BRIDGE_HOST = "0.0.0.0"
DEFAULT_BRIDGE_PORT = 8787
DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 8000
DEFAULT_SERVER_PATH = "/mcp"


def _server_url(host: str, port: int, path: str) -> str:
    return f"http://{host}:{port}{path}"


def _bridge_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


async def _pipe_output(name: str, stream: asyncio.StreamReader | None) -> None:
    if stream is None:
        return
    while True:
        line = await stream.readline()
        if not line:
            return
        print(f"[{name}] {line.decode().rstrip()}")


async def _start_process(name: str, *cmd: str, cwd: Path) -> tuple[asyncio.subprocess.Process, asyncio.Task[None]]:
    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    log_task = asyncio.create_task(_pipe_output(name, process.stdout))
    return process, log_task


async def _stop_process(process: asyncio.subprocess.Process, log_task: asyncio.Task[None]) -> None:
    if process.returncode is None:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
    await log_task


async def _wait_for_bridge(bridge_url: str) -> None:
    async with httpx.AsyncClient(timeout=1.0) as client:
        for _ in range(60):
            try:
                r = await client.get(f"{bridge_url}/health")
                if r.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.25)
    raise RuntimeError(f"Bridge never became ready at {bridge_url}.")


async def _wait_for_mcp(server_url: str) -> None:
    last_error: Exception | None = None
    for _ in range(60):
        try:
            client = await MCPClient.connect(server_url)
            async with client:
                await client.list_tools()
            return
        except Exception as e:
            last_error = e
            await asyncio.sleep(0.25)
    raise RuntimeError(f"MCP server never became ready at {server_url}: {last_error}") from last_error


async def _join_game(server_url: str, host: str, port: int, username: str, auth: str) -> bool:
    async with await MCPClient.connect(server_url) as client:
        result = await client.call_tool(
            "join_game",
            {"host": host, "port": port, "username": username, "auth": auth},
        )
        for c in result.content:
            if c.type == "text":
                data = json.loads(c.text)
                if data.get("connected"):
                    print(f"[launcher] Joined game at {host}:{port} as {data.get('username', username)}")
                    return True
                print(f"[launcher] Join failed: {data.get('error', c.text)}")
                return False
    return False


async def _run(args: argparse.Namespace) -> None:
    bridge_url = _bridge_url(args.bridge_host, args.bridge_port)
    server_url = _server_url(args.server_host, args.server_port, args.server_path)

    print("[launcher] Starting bridge (real mode)...")
    bridge_process, bridge_logs = await _start_process(
        "bridge",
        "npm",
        "--prefix",
        "bridge",
        "run",
        "start",
        "--",
        "--listen-host",
        args.bridge_host,
        "--listen-port",
        str(args.bridge_port),
        cwd=ROOT,
    )
    mcp_process: asyncio.subprocess.Process | None = None
    mcp_logs: asyncio.Task[None] | None = None

    try:
        await _wait_for_bridge(bridge_url)
        print("[launcher] Starting MCP server...")
        mcp_process, mcp_logs = await _start_process(
            "mcp",
            sys.executable,
            "-m",
            "minecraft_dedalus_mcp.server",
            "--host",
            args.server_host,
            "--port",
            str(args.server_port),
            "--path",
            args.server_path,
            "--bridge-url",
            bridge_url,
            cwd=ROOT,
        )
        await _wait_for_mcp(server_url)
        print(f"[launcher] Ready: bridge {bridge_url}, MCP {server_url}")

        joined = await _join_game(
            server_url,
            host=args.join_host,
            port=args.join_port,
            username=args.username,
            auth=args.auth,
        )
        if not joined:
            print("[launcher] Could not join the game. Open a world to LAN and note the port, then restart with --join-host and --join-port.")
            print("[launcher] Continuing anyway; you can run run_join_game.py manually and chat commands will work once the bot is in.")

        if not os.getenv("DEDALUS_API_KEY"):
            print("[launcher] DEDALUS_API_KEY not set. Set it in .env to enable chat commands.")
            print("[launcher] Bridge and MCP server are running. Press Ctrl+C to stop.")
            while True:
                await asyncio.sleep(3600)
        else:
            server_url_for_agent = args.agent_mcp_url or server_url
            print("[launcher] Starting chat agent. Type in Minecraft chat to command the bot. Ctrl+C to stop.")
            from run_chat_agent import main_async as run_chat_main_async
            await run_chat_main_async(
                mcp_url=server_url,
                server_url=server_url_for_agent,
                poll_interval=args.poll_interval,
                chat_limit=args.chat_limit,
                continue_after=args.continue_after,
                rate_limit_wait_sec=args.rate_limit_wait,
            )
    finally:
        if mcp_process is not None and mcp_logs is not None:
            await _stop_process(mcp_process, mcp_logs)
        await _stop_process(bridge_process, bridge_logs)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Start bridge, MCP server, join the game, and run the chat-driven agent. Command the bot via in-game chat."
    )
    p.add_argument("--bridge-host", default=DEFAULT_BRIDGE_HOST, help="Bridge listen host")
    p.add_argument("--bridge-port", type=int, default=DEFAULT_BRIDGE_PORT, help="Bridge listen port")
    p.add_argument("--server-host", default=DEFAULT_SERVER_HOST, help="MCP server host")
    p.add_argument("--server-port", type=int, default=DEFAULT_SERVER_PORT, help="MCP server port")
    p.add_argument("--server-path", default=DEFAULT_SERVER_PATH, help="MCP server path")
    p.add_argument(
        "--join-host",
        default=os.environ.get("MINECRAFT_HOST", "127.0.0.1"),
        help="Minecraft server host (e.g. 192.168.68.70 for LAN; set MINECRAFT_HOST)",
    )
    p.add_argument(
        "--join-port",
        type=int,
        default=int(os.environ.get("MINECRAFT_PORT", "25565")),
        help="Minecraft server port (LAN port from in-game; set MINECRAFT_PORT)",
    )
    p.add_argument("--username", default=os.environ.get("MINECRAFT_USERNAME", "DedalusBot"))
    p.add_argument("--auth", default="microsoft", choices=("microsoft", "offline"))
    p.add_argument(
        "--agent-mcp-url",
        default=os.environ.get("AGENT_MCP_URL", ""),
        help="MCP URL for the Dedalus agent (use ngrok URL so cloud can reach your MCP; e.g. https://xxx.ngrok.io/mcp)",
    )
    p.add_argument("--poll-interval", type=float, default=8.0, help="Chat poll interval (seconds)")
    p.add_argument("--chat-limit", type=int, default=20, help="Chat messages to fetch per poll")
    p.add_argument(
        "--continue-after",
        type=int,
        default=100,
        help="After this many agent runs, prompt to continue (0 = never). Helps avoid rate limits.",
    )
    p.add_argument(
        "--rate-limit-wait",
        type=float,
        default=60.0,
        help="When rate limit is detected, wait this many seconds before offering to continue.",
    )
    args = p.parse_args()
    if not args.agent_mcp_url:
        args.agent_mcp_url = _server_url(args.server_host, args.server_port, args.server_path)
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("\n[launcher] Stopped.")


if __name__ == "__main__":
    main()
