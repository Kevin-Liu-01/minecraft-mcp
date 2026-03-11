# Research Notes

Date: March 11, 2026

## Goal

Build a Minecraft MCP that:

- works over LAN
- can control a bot for building and survival progression
- uses the Dedalus Python SDK and Dedalus MCP framework
- remains locally testable without a human opening a LAN world every loop

## Sources Reviewed

### Dedalus

- Dedalus SDK docs: `sdk/quickstart`, `sdk/mcp`, `dmcp/quickstart`
- [`dedalus-labs/dedalus-sdk-python`](https://github.com/dedalus-labs/dedalus-sdk-python)
- [`dedalus-labs/dedalus-mcp-python`](https://github.com/dedalus-labs/dedalus-mcp-python)

Relevant takeaways:

- `dedalus_labs` exposes `AsyncDedalus` and `DedalusRunner`
- `DedalusRunner.run(..., mcp_servers=[...])` accepts MCP URLs directly
- `dedalus_mcp` exposes `MCPServer` and `MCPClient`
- the default HTTP MCP endpoint pattern is `http://127.0.0.1:8000/mcp`

### Existing Minecraft MCPs and bot stacks

- [`yuniko-software/minecraft-mcp-server`](https://github.com/yuniko-software/minecraft-mcp-server)
- [`FundamentalLabs/minecraft-mcp`](https://github.com/FundamentalLabs/minecraft-mcp)
- [`PrismarineJS/mineflayer`](https://github.com/PrismarineJS/mineflayer)
- [`MineDojo/Voyager`](https://github.com/MineDojo/Voyager)
- [`mcpq/mcpq-python`](https://github.com/mcpq/mcpq-python)
- [`ammaraskar/pyCraft`](https://github.com/ammaraskar/pyCraft)
- [`PrismarineJS/flying-squid`](https://github.com/PrismarineJS/flying-squid)

## What existing projects do well

### `yuniko-software/minecraft-mcp-server`

Strengths:

- dead simple MCP surface
- explicitly targets LAN worlds and Mineflayer
- useful low-level tools for movement, inventory, blocks, chat

Weaknesses:

- narrower skill surface than the larger projects
- Node-only stack, no Dedalus-native Python integration

Port value:

- low-level MCP tool naming and LAN connection ergonomics

### `FundamentalLabs/minecraft-mcp`

Strengths:

- large skill catalog
- verified survival tasks like `mineResource`, `craftItems`, `goToKnownLocation`
- explicit building helpers like `buildSomething`

Weaknesses:

- some building flows rely on commands or cheats
- still Node-first

Port value:

- high-level skill decomposition and naming conventions

### `Mineflayer`

Strengths:

- best-supported JS bot runtime for Minecraft Java Edition
- pathfinding, crafting, digging, combat, inventory, chat
- proven in both hobby and research projects

Weaknesses:

- JS runtime only
- you still have to build the agent/MCP layer yourself

Port value:

- this is the actual world-control substrate for the bridge

### `Voyager`

Strengths:

- strongest inspiration for iterative skill acquisition and staged progression
- proven Minecraft task decomposition

Weaknesses:

- much heavier research stack than needed for a local MCP
- old environment assumptions

Port value:

- playbook and phased survival progression ideas, not direct code reuse

### `mcpq-python`

Strengths:

- Python-native control
- very nice for building and turtle-like structured world edits

Weaknesses:

- requires a Paper/Spigot plugin
- more server-plugin-centric than player-bot-centric
- not a great survival agent substrate for "beat Minecraft"

Port value:

- interesting alternative for build-only workflows

### `pyCraft`

Strengths:

- Python client

Weaknesses:

- limited protocol surface compared with Mineflayer
- older supported version story
- not an obvious fit for modern survival automation

Port value:

- rejected for this project

## Architecture decision

Chosen architecture:

- Python Dedalus MCP server
- Node Mineflayer bridge
- simulation mode for repeatable e2e validation

Why:

- best survival bot substrate is still Mineflayer
- best Dedalus integration is still Python
- simulation closes the testing gap that most Minecraft MCP repos leave wide open

Rejected alternatives:

- Pure RCON or command-only control:
  - fine for creative building
  - not credible for survival or legitimate progression
- Pure Python bot stack:
  - weaker modern protocol/control story
- Paper plugin only:
  - great for structured edits, weaker for actual player-like survival

## Porting decisions in this repo

Directly ported in spirit:

- `joinGame` -> `join_game`
- `goToKnownLocation` -> `go_to_known_location`
- `mineResource` -> `mine_resource`
- `craftItems` -> `craft_items`
- `attackSomeone` -> `attack_entity`
- `buildSomething` -> `build_structure`
- `lookAround` / environment scan -> `inspect_world`

Inspired by Voyager:

- `recommend_next_goal` survival playbook
- staged progression from wood to dragon prep

## Testing strategy

Main problem:

- real LAN worlds are annoying to keep open for automated iteration

Solution:

- simulation mode in the bridge
- Python MCP e2e tests that talk to the simulated bridge over HTTP
- optional real-world smoke testing can be layered on later with a local server such as `flying-squid`

## Why this is workable

- Dedalus SDK natively accepts MCP URLs
- Dedalus MCP server can expose the ported Minecraft tool surface cleanly
- Mineflayer already solves the hard in-world mechanics
- simulation mode gives a deterministic test target

