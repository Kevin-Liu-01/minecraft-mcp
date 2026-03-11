# Minecraft Dedalus MCP

`minecraft-dedalus-mcp` is a LAN-oriented Minecraft MCP stack with three layers:

1. A Python MCP server built on [`dedalus_mcp`](https://github.com/dedalus-labs/dedalus-mcp-python).
2. A Node bridge that talks to a real Minecraft bot through [Mineflayer](https://github.com/PrismarineJS/mineflayer).
3. A simulation mode so the whole thing can be tested end to end without manually opening a LAN world every time.

The result is a local project you can point the Dedalus Python SDK at, then ask an agent to gather resources, craft, build, and work through a survival playbook for beating Minecraft.

## Why this shape

Mineflayer remains the most mature Java Edition bot runtime for real survival actions over LAN. The Dedalus Python SDK and `dedalus_mcp` make the agent and MCP surface cleaner in Python, so this project splits the system where each toolchain is strongest:

- Node handles world interaction.
- Python handles MCP ergonomics, planning, and Dedalus integration.

The detailed comparison is in [docs/research.md](docs/research.md).

## Features

- LAN-ready bridge and MCP server, both bindable to `0.0.0.0`
- Real Mineflayer mode for Java Edition LAN worlds or local servers
- Simulation mode for fast repeatable tests
- Ported capability surface inspired by existing Minecraft MCP projects:
  - `join_game`
  - `go_to_known_location`
  - `mine_resource`
  - `craft_items`
  - `build_structure`
  - `attack_entity`
  - `inspect_world`
  - `recommend_next_goal`
- Dedalus agent demo using `DedalusRunner`

## Requirements

- Python 3.10+ (`uv` will manage this automatically)
- Node 20+
- npm 10+

For real LAN control:

- Minecraft Java Edition world opened to LAN, or a local Paper/Spigot/offline test server
- A bot account or offline-mode server, depending on your setup

## Setup

Install Python deps:

```bash
uv sync --extra dev
```

Install bridge deps:

```bash
npm --prefix bridge install
```

## Run the simulated stack

Fast path, one command:

```bash
export DEDALUS_API_KEY=your_key_here
uv run minecraft-dedalus-run-sim
```

That one command:

- starts the simulated bridge
- starts the MCP server
- waits until both are ready
- runs the Dedalus agent against your local MCP
- shuts everything down when the run finishes

You can override the goal:

```bash
export DEDALUS_API_KEY=your_key_here
uv run minecraft-dedalus-run-sim \
  --goal "Call join_game with host 127.0.0.1, port 25565, username DedalusBot, and auth offline. Then inspect_world, mine 4 oak_log, craft 16 oak_planks, and build a hut."
```

If you just want the launcher to boot the stack and verify readiness without spending tokens:

```bash
uv run minecraft-dedalus-run-sim --skip-agent
```

Manual mode, if you want separate terminals:

Terminal 1:

```bash
npm --prefix bridge run simulate
```

Terminal 2:

```bash
uv run python -m minecraft_dedalus_mcp.server --bridge-url http://127.0.0.1:8787
```

Optional Terminal 3, if you want to use the Dedalus SDK:

```bash
export DEDALUS_API_KEY=your_key_here
uv run python -m minecraft_dedalus_mcp.agent_demo \
  --server-url http://127.0.0.1:8000/mcp \
  --goal "Join the simulated world, gather wood, craft planks, and build a pillar."
```

## Run against a real LAN world

Start the bridge:

```bash
npm --prefix bridge run start -- --listen-host 0.0.0.0 --listen-port 8787
```

Start the MCP server:

```bash
uv run python -m minecraft_dedalus_mcp.server \
  --host 0.0.0.0 \
  --port 8000 \
  --bridge-url http://127.0.0.1:8787
```

Then call the MCP tool:

```text
join_game(host="192.168.1.42", port=54017, username="DedalusBot", auth="microsoft")
```

Notes:

- For a vanilla singleplayer world opened to LAN, you usually want `auth="microsoft"` and a second licensed account.
- For offline-mode local servers, `auth="offline"` is simpler and easier for bot testing.
- The bridge and MCP server can live on the same box as Minecraft or on a separate machine on your LAN.

## Testing

Run the automated suite:

```bash
uv run pytest
```

The e2e tests start:

- the Node bridge in simulation mode
- the Python MCP server
- a real `MCPClient`

So they exercise the actual transport path rather than just unit mocks.

## Project layout

```text
bridge/                      Node Mineflayer bridge + simulator
docs/research.md             Research notes and porting rationale
src/minecraft_dedalus_mcp/   Python MCP server, bridge client, playbook
tests/                       Unit and e2e tests
```

## Current limitations

- The simulation mode validates tool behavior and orchestration, not Mineflayer physics.
- The real bridge supports core survival actions, but it is not yet a full Voyager-class autonomous stack.
- Beating Minecraft is expressed as a staged playbook and agent workflow, not a one-click guaranteed dragon kill.
