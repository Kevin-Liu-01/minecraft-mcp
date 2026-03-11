from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from dedalus_mcp.client import MCPClient


ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


async def _wait_for_http(url: str, *, attempts: int = 40, delay: float = 0.25) -> None:
    async with httpx.AsyncClient(timeout=2.0) as client:
        for _ in range(attempts):
            try:
                response = await client.get(url)
                if response.status_code < 500:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(delay)
    raise RuntimeError(f"Timed out waiting for {url}")


@asynccontextmanager
async def _bridge_process(port: int) -> AsyncIterator[subprocess.Popen[str]]:
    process = subprocess.Popen(
        ["node", "server.mjs", "--simulate", "--listen-host", "127.0.0.1", "--listen-port", str(port)],
        cwd=ROOT / "bridge",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        await _wait_for_http(f"http://127.0.0.1:{port}/health")
        yield process
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


@asynccontextmanager
async def _mcp_process(port: int, bridge_port: int) -> AsyncIterator[subprocess.Popen[str]]:
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "minecraft_dedalus_mcp.server",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--bridge-url",
            f"http://127.0.0.1:{bridge_port}",
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        await _wait_for_http(f"http://127.0.0.1:{port}/mcp")
        yield process
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


@pytest.mark.asyncio
async def test_simulated_bridge_end_to_end() -> None:
    bridge_port = _free_port()
    mcp_port = _free_port()

    async with _bridge_process(bridge_port), _mcp_process(mcp_port, bridge_port):
        client = await MCPClient.connect(f"http://127.0.0.1:{mcp_port}/mcp")
        async with client:
            tools = await client.list_tools()
            tool_names = {tool.name for tool in tools.tools}
            assert "join_game" in tool_names
            assert "recommend_next_goal" in tool_names

            join_result = await client.call_tool(
                "join_game",
                {
                    "host": "127.0.0.1",
                    "port": 25565,
                    "username": "TestBot",
                    "auth": "offline",
                },
            )
            join_payload = json.loads(join_result.content[0].text)
            assert join_payload["connected"] is True
            assert join_payload["username"] == "TestBot"

            mine_result = await client.call_tool("mine_resource", {"name": "oak_log", "count": 2})
            mine_payload = json.loads(mine_result.content[0].text)
            assert mine_payload["mined"] == 2

            craft_result = await client.call_tool("craft_items", {"item": "oak_planks", "count": 8})
            craft_payload = json.loads(craft_result.content[0].text)
            assert craft_payload["crafted"] >= 8

            build_result = await client.call_tool(
                "build_structure",
                {
                    "preset": "pillar",
                    "material": "cobblestone",
                    "origin_x": 2,
                    "origin_y": 64,
                    "origin_z": 2,
                    "height": 3,
                },
            )
            build_payload = json.loads(build_result.content[0].text)
            assert build_payload["blocks_placed"] == 3

            status_result = await client.call_tool("get_bot_status", {})
            status_payload = json.loads(status_result.content[0].text)
            inventory_names = {entry["item"] for entry in status_payload["inventory"]}
            assert "oak_planks" in inventory_names

            recommendation_result = await client.call_tool("recommend_next_goal", {"goal": "build-house"})
            recommendation_payload = json.loads(recommendation_result.content[0].text)
            assert recommendation_payload["phase"] in {"gather-wood", "build-starter-hut"}
