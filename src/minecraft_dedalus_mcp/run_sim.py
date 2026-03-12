from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx
from dedalus_mcp.client import MCPClient
from dotenv import load_dotenv

from .agent_demo import run_agent


load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 8000
DEFAULT_SERVER_PATH = "/mcp"
DEFAULT_BRIDGE_HOST = "127.0.0.1"
DEFAULT_BRIDGE_PORT = 8787


def _server_url(host: str, port: int, path: str) -> str:
    return f"http://{host}:{port}{path}"


def _bridge_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def _default_goal(join_host: str, join_port: int, username: str, auth: str) -> str:
    return (
        f"Call join_game with host {join_host}, port {join_port}, username {username}, and auth {auth}. "
        "Then inspect_world, mine 4 oak_log, craft 16 oak_planks, and build a hut."
    )


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
                response = await client.get(f"{bridge_url}/health")
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.25)
    raise RuntimeError(f"Bridge never became ready at {bridge_url}.")


async def _wait_for_mcp(server_url: str) -> None:
    last_error: Exception | None = None
    for _ in range(60):
        client: MCPClient | None = None
        try:
            client = await MCPClient.connect(server_url)
            async with client:
                await client.list_tools()
            return
        except Exception as error:  # pragma: no cover - readiness failures are timing-sensitive
            last_error = error
            await asyncio.sleep(0.25)
    if last_error is None:
        raise RuntimeError(f"MCP server never became ready at {server_url}.")
    raise RuntimeError(f"MCP server never became ready at {server_url}: {last_error}") from last_error


async def _run_launcher(args: argparse.Namespace) -> None:
    bridge_url = _bridge_url(args.bridge_host, args.bridge_port)
    server_url = _server_url(args.server_host, args.server_port, args.server_path)
    goal = args.goal or _default_goal(args.join_host, args.join_port, args.username, args.auth)

    print(f"Starting simulated bridge at {bridge_url}")
    bridge_process, bridge_logs = await _start_process(
        "bridge",
        "npm",
        "--prefix",
        "bridge",
        "run",
        "simulate",
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

        print(f"Starting MCP server at {server_url}")
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
        print(f"Ready: bridge {bridge_url}, MCP {server_url}")

        if args.skip_agent:
            print("Skipping Dedalus agent run by request.")
            return

        await run_agent(
            server_url=server_url,
            model=args.model,
            goal=goal,
            max_steps=args.max_steps,
        )
    finally:
        if mcp_process is not None and mcp_logs is not None:
            await _stop_process(mcp_process, mcp_logs)
        await _stop_process(bridge_process, bridge_logs)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Start the simulated Minecraft bridge, MCP server, and Dedalus agent in one command"
    )
    parser.add_argument("--bridge-host", default=DEFAULT_BRIDGE_HOST)
    parser.add_argument("--bridge-port", type=int, default=DEFAULT_BRIDGE_PORT)
    parser.add_argument("--server-host", default=DEFAULT_SERVER_HOST)
    parser.add_argument("--server-port", type=int, default=DEFAULT_SERVER_PORT)
    parser.add_argument("--server-path", default=DEFAULT_SERVER_PATH)
    parser.add_argument("--join-host", default="127.0.0.1")
    parser.add_argument("--join-port", type=int, default=25565)
    parser.add_argument("--username", default="DedalusBot")
    parser.add_argument("--auth", default="offline")
    parser.add_argument("--model", default=os.environ.get("DEDALUS_MODEL", "openai/gpt-4o-mini"))
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--goal")
    parser.add_argument(
        "--skip-agent",
        action="store_true",
        help="Start the simulated bridge and MCP server, verify readiness, then exit without calling Dedalus.",
    )
    try:
        asyncio.run(_run_launcher(parser.parse_args()))
    except KeyboardInterrupt:
        print("Launcher interrupted.")
    except RuntimeError as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
